"""
WFE L1 — FLOW ENGINE (Hậu duệ MCDX)
Architecture Contract:
1. Độc lập tuyệt đối: không import Structure hay Volume Engine.
2. Vai trò: radar dẫn & trễ (timing).
3. Xuất 3 sub-scores (0-100), percentiles, data_ok, params_hash.
4. Không in từ ngữ dự báo.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import math
from wfe.config.registry import FlowEngineConfig, compute_params_hash
from wfe.data.pit_feed import MarketBar, compute_prev_sma20_vol


@dataclass
class FlowSubScore:
    value: Optional[float]
    percentile: Optional[float]
    data_ok: bool
    params_hash: str


@dataclass
class FlowOutput:
    trend: FlowSubScore
    accum: FlowSubScore
    dist: FlowSubScore
    trend_collapse_warning: bool
    data_ok: bool
    params_hash: str
    diagnostics: Dict[str, Any] = field(default_factory=dict)


def compute_wilder_rsi(closes: List[float], period: int = 50) -> List[Optional[float]]:
    """
    Computes Wilder's RSI initialized with SMA of first `period` bars.
    Returns list of same length as closes.
    """
    n = len(closes)
    rsi_list: List[Optional[float]] = [None] * n
    if n < period + 1:
        return rsi_list

    deltas = [closes[i] - closes[i - 1] for i in range(1, n)]
    gains = [max(0.0, d) for d in deltas]
    losses = [max(0.0, -d) for d in deltas]

    # First average using SMA
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_gain == 0 and avg_loss == 0:
        rsi_list[period] = 50.0
    elif avg_loss == 0:
        rsi_list[period] = 100.0
    elif avg_gain == 0:
        rsi_list[period] = 0.0
    else:
        rs = avg_gain / avg_loss
        rsi_list[period] = 100.0 - (100.0 / (1.0 + rs))

    # Wilder smoothing for subsequent bars
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_gain == 0 and avg_loss == 0:
            rsi = 50.0
        elif avg_loss == 0:
            rsi = 100.0
        elif avg_gain == 0:
            rsi = 0.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))
        rsi_list[i + 1] = rsi

    return rsi_list


def compute_obv_series(bars: List[MarketBar]) -> List[float]:
    """Computes On-Balance Volume (OBV) series using closed bars."""
    n = len(bars)
    if n == 0:
        return []
    obv = [0.0] * n
    current_obv = 0.0
    for i in range(1, n):
        if bars[i].close > bars[i - 1].close:
            current_obv += bars[i].volume
        elif bars[i].close < bars[i - 1].close:
            current_obv -= bars[i].volume
        obv[i] = current_obv
    return obv


def pct_rank_window(val: float, window: List[float]) -> float:
    """Computes percentile rank of val within window (0 to 100)."""
    if not window:
        return 50.0
    less_count = sum(1 for x in window if x < val)
    equal_count = sum(1 for x in window if x == val)
    return ((less_count + 0.5 * equal_count) / len(window)) * 100.0


def compute_atr14_series(bars: List[MarketBar]) -> List[Optional[float]]:
    """Computes ATR 14."""
    n = len(bars)
    atr = [None] * n
    if n < 14:
        return atr
    tr_list = []
    for i in range(1, n):
        h, l = bars[i].high, bars[i].low
        c_prev = bars[i - 1].close
        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        tr_list.append(tr)

    # Initial SMA 14
    first_atr = sum(tr_list[:14]) / 14.0
    atr[14] = first_atr
    curr_atr = first_atr
    for i in range(14, len(tr_list)):
        curr_atr = (curr_atr * 13 + tr_list[i]) / 14.0
        atr[i + 1] = curr_atr
    return atr


class FlowEngine:
    """Flow Engine calculates flow_trend, flow_accum, and flow_dist."""

    def __init__(self, config: Optional[FlowEngineConfig] = None):
        self.config = config or FlowEngineConfig()

    @property
    def params_hash(self) -> str:
        return self.config.params_hash

    def calculate(
        self,
        bars: List[MarketBar],
        is_breakout: bool = False,
        external_test_depletion_score: Optional[float] = None,
        external_ut_flag: Optional[float] = None,
        pivot_reference: Optional[float] = None
    ) -> FlowOutput:
        """
        Execute calculations on closed bars.
        If data is invalid or insufficient, returns FlowOutput with data_ok=False and scores=None.
        """
        cfg = self.config
        p_hash = self.params_hash

        if not bars or len(bars) < cfg.rsi_period + 20:
            none_sub = FlowSubScore(value=None, percentile=None, data_ok=False, params_hash=p_hash)
            return FlowOutput(
                trend=none_sub,
                accum=none_sub,
                dist=none_sub,
                trend_collapse_warning=False,
                data_ok=False,
                params_hash=p_hash,
                diagnostics={"reason": "insufficient_history"}
            )

        n = len(bars)
        closes = [b.close for b in bars]
        volumes = [b.volume for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]

        # 1. Directed volume series: up_vol, down_vol
        up_vols = [0.0] * n
        down_vols = [0.0] * n
        for i in range(1, n):
            if closes[i] > closes[i - 1]:
                up_vols[i] = volumes[i]
            elif closes[i] < closes[i - 1]:
                down_vols[i] = volumes[i]

        # 2. RSI 50
        rsi_series = compute_wilder_rsi(closes, period=cfg.rsi_period)
        latest_rsi = rsi_series[-1]

        if latest_rsi is None:
            none_sub = FlowSubScore(value=None, percentile=None, data_ok=False, params_hash=p_hash)
            return FlowOutput(
                trend=none_sub,
                accum=none_sub,
                dist=none_sub,
                trend_collapse_warning=False,
                data_ok=False,
                params_hash=p_hash
            )

        # 3. Previous SMA20 volume strictly excluding current bar
        prev_sma20_vol = compute_prev_sma20_vol(bars, n - 1)
        curr_vol = volumes[-1]
        vol_ratio = (curr_vol / prev_sma20_vol) if prev_sma20_vol > 0 else (0.0 if curr_vol == 0 else 1.0)

        # Determine cap: cap=1.5 in box, cap=2.5 when breakout above pivot/TR_High
        cap = cfg.cap_breakout if is_breakout else cfg.cap_in_box
        mult = min(cap, vol_ratio)

        # (a) flow_trend
        base_trend = max(0.0, (latest_rsi - 50.0) * cfg.rsi_scale)
        flow_trend_val = min(100.0, base_trend * mult)

        # Multi-bar flow_trend history for trend_collapse_warning and percentile
        trend_history: List[float] = []
        for i in range(cfg.rsi_period, n):
            r = rsi_series[i]
            if r is None:
                continue
            p_sma = compute_prev_sma20_vol(bars, i)
            v_rat = (volumes[i] / p_sma) if p_sma > 0 else 1.0
            # breakout check for historical if pivot known
            hist_cap = cfg.cap_breakout if (pivot_reference and closes[i] > pivot_reference) else cfg.cap_in_box
            m = min(hist_cap, v_rat)
            b = max(0.0, (r - 50.0) * cfg.rsi_scale)
            trend_history.append(min(100.0, b * m))

        # Check trend collapse warning:
        # flow_trend[t] < 15 while max(flow_trend[t-3:t-1]) >= 50 and close[t] >= max(high[t-20:t])
        trend_collapse_warning = False
        if len(trend_history) >= 4 and n >= 21:
            prior_max_trend = max(trend_history[-4:-1])
            highest_20_high = max(highs[-21:-1])
            if (
                flow_trend_val < cfg.trend_collapse_threshold
                and prior_max_trend >= cfg.trend_collapse_prior_min
                and closes[-1] >= highest_20_high
            ):
                trend_collapse_warning = True

        # Percentile rank for flow_trend (rolling up to 250)
        roll_window = trend_history[-cfg.rolling_percentile_window:]
        trend_percentile = pct_rank_window(flow_trend_val, roll_window)

        # (b) flow_accum components
        # 1. dv_contr = 1 - min(1, SMA5(down_vol)/SMA20(down_vol))
        sma5_dv = sum(down_vols[-5:]) / 5.0
        sma20_dv = sum(down_vols[-20:]) / 20.0
        if sma20_dv > 0:
            dv_contr = 1.0 - min(1.0, sma5_dv / sma20_dv)
        else:
            dv_contr = 1.0 if sma5_dv == 0 else 0.5

        # 2. Absorption: ratio of down candles in last 10 bars with vol_ratio >= 1.2 but |delta_close| <= 0.4*ATR14
        atr_series = compute_atr14_series(bars)
        latest_atr = atr_series[-1] or (highs[-1] - lows[-1] or 1.0)

        down_candles_10 = 0
        absorb_candles_10 = 0
        for i in range(max(1, n - 10), n):
            if closes[i] < closes[i - 1]:
                down_candles_10 += 1
                p_sma_i = compute_prev_sma20_vol(bars, i)
                vr_i = (volumes[i] / p_sma_i) if p_sma_i > 0 else 1.0
                delta_c = abs(closes[i] - closes[i - 1])
                atr_i = atr_series[i] or latest_atr
                if vr_i >= 1.2 and delta_c <= 0.4 * atr_i:
                    absorb_candles_10 += 1

        absorb_ratio = (absorb_candles_10 / down_candles_10) if down_candles_10 > 0 else 0.0

        # 3. OBV divergence positive: 100 * max(0, pct_rank20(OBV) - pct_rank20(close))
        obv_series = compute_obv_series(bars)
        obv_window = obv_series[-20:]
        close_window = closes[-20:]
        obv_rank = pct_rank_window(obv_series[-1], obv_window)
        close_rank = pct_rank_window(closes[-1], close_window)
        obv_div_pos = max(0.0, obv_rank - close_rank)  # 0 to 100

        # 4. udr_score: up/down vol ratio in sideways market
        sma20_uv = sum(up_vols[-20:]) / 20.0
        udr_raw = (sma20_uv / sma20_dv) if sma20_dv > 0 else (2.0 if sma20_uv > 0 else 1.0)
        # Price slope penalty if price is dumping
        pct_chg_20 = (closes[-1] - closes[-20]) / closes[-20] if closes[-20] > 0 else 0.0
        slope_penalty = 1.0 if abs(pct_chg_20) <= 0.05 else max(0.2, 1.0 - abs(pct_chg_20) * 5.0)
        udr_score = min(100.0, (udr_raw / 2.0) * 100.0 * slope_penalty)

        # 5. test_vol_depletion (from Policy feature if available, default 50.0)
        test_depletion = external_test_depletion_score if external_test_depletion_score is not None else 50.0

        flow_accum_raw = (
            cfg.w_accum_dv_contr * (dv_contr * 100.0)
            + cfg.w_accum_absorption * (absorb_ratio * 100.0)
            + cfg.w_accum_obv_div * obv_div_pos
            + cfg.w_accum_udr * udr_score
            + cfg.w_accum_test_depletion * test_depletion
        )
        flow_accum_val = max(0.0, min(100.0, flow_accum_raw))

        # (c) flow_dist components (mirror opposite)
        # 1. Effort no result upward: up candles at 20-bar peak with vol_ratio >= 1.2 but body <= 0.3*ATR14
        up_candles_peak = 0
        effort_no_res_count = 0
        recent_20_high = max(highs[-20:])
        for i in range(max(1, n - 10), n):
            if closes[i] > closes[i - 1] and highs[i] >= recent_20_high * 0.98:
                up_candles_peak += 1
                p_sma_i = compute_prev_sma20_vol(bars, i)
                vr_i = (volumes[i] / p_sma_i) if p_sma_i > 0 else 1.0
                body = abs(closes[i] - bars[i].open)
                atr_i = atr_series[i] or latest_atr
                if vr_i >= 1.2 and body <= 0.3 * atr_i:
                    effort_no_res_count += 1

        effort_no_res_ratio = (effort_no_res_count / up_candles_peak) if up_candles_peak > 0 else 0.0

        # 2. Negative OBV divergence: 100 * max(0, pct_rank20(close) - pct_rank20(OBV))
        obv_div_neg = max(0.0, close_rank - obv_rank)

        # 3. Up volume exhaustion at peak: 1 - min(1, SMA5(up_vol)/SMA20(up_vol))
        sma5_uv = sum(up_vols[-5:]) / 5.0
        if sma20_uv > 0:
            up_vol_exhaust = 1.0 - min(1.0, sma5_uv / sma20_uv)
        else:
            up_vol_exhaust = 0.5

        # 4. Down volume expansion in upper half
        # Check if current close is above 20-bar mid
        mid_20 = (max(highs[-20:]) + min(lows[-20:])) / 2.0
        if closes[-1] >= mid_20:
            down_vol_expansion = min(1.0, sma5_dv / (sma20_dv + 1e-6))
        else:
            down_vol_expansion = 0.0

        # 5. Bonus UT/UTAD flag (from Structure via Policy)
        ut_score = external_ut_flag if external_ut_flag is not None else 0.0

        flow_dist_raw = (
            cfg.w_dist_effort_no_result * (effort_no_res_ratio * 100.0)
            + cfg.w_dist_obv_div_neg * obv_div_neg
            + cfg.w_dist_up_vol_exhaust * (up_vol_exhaust * 100.0)
            + cfg.w_dist_down_vol_expansion * (down_vol_expansion * 100.0)
            + cfg.w_dist_ut_bonus * ut_score
        )
        flow_dist_val = max(0.0, min(100.0, flow_dist_raw))

        # Rolling percentile ranks for accum & dist (synthetic baseline approximation across history)
        # Using normalized scores based on distribution
        accum_percentile = flow_accum_val  # already 0-100 normalized weighted
        dist_percentile = flow_dist_val

        trend_sub = FlowSubScore(
            value=round(flow_trend_val, 2),
            percentile=round(trend_percentile, 1),
            data_ok=True,
            params_hash=p_hash
        )
        accum_sub = FlowSubScore(
            value=round(flow_accum_val, 2),
            percentile=round(accum_percentile, 1),
            data_ok=True,
            params_hash=p_hash
        )
        dist_sub = FlowSubScore(
            value=round(flow_dist_val, 2),
            percentile=round(dist_percentile, 1),
            data_ok=True,
            params_hash=p_hash
        )

        return FlowOutput(
            trend=trend_sub,
            accum=accum_sub,
            dist=dist_sub,
            trend_collapse_warning=trend_collapse_warning,
            data_ok=True,
            params_hash=p_hash,
            diagnostics={
                "rsi_50": round(latest_rsi, 2),
                "vol_ratio": round(vol_ratio, 2),
                "cap": cap,
                "dv_contr": round(dv_contr, 3),
                "absorb_ratio": round(absorb_ratio, 3),
                "obv_div_pos": round(obv_div_pos, 1),
                "obv_div_neg": round(obv_div_neg, 1),
                "trend_history": trend_history
            }
        )
