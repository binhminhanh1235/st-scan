"""
WFE SKILL_9 — MCDX FLOW RADAR (V3.0)
Radar lọc ứng viên theo dòng tiền tạo lập: ESTABLISHED & EMERGING.
Architecture Contract:
1. Chỉ tiêu thụ đầu ra của Flow Engine (L1). Không tính lại MCDX, không gọi Structure hay Volume Engine.
2. Không xuất target/stop, không gán nhãn pha Wyckoff, không hứa hẹn sóng.
3. Chế độ ESTABLISHED (E1-E4) và EMERGING (G1 flow-turn / G2 gom bí mật).
4. Tính Banker Intensity Index (BII 0-100).
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
import numpy as np
from wfe.config.registry import MCDXRadarConfig, DEFAULT_REGISTRY, compute_params_hash
from wfe.data.pit_feed import MarketBar, compute_prev_sma20_vol
from wfe.engines.flow_engine import FlowEngine, FlowOutput
from wfe.ops.governance import KillSwitchManager

STANDARD_MCDX_DISCLAIMER = (
    "Lưu ý Hệ thống: MCDX là proxy heuristic từ giá và khối lượng công khai, "
    "không phải sổ lệnh thật của tạo lập. Danh sách trả về là radar ứng viên theo dõi dòng tiền, "
    "không phải khuyến nghị mua/bán."
)


@dataclass
class MCDXCandidate:
    symbol: str
    current_price: float
    adtv20_bil: float
    flow_trend: float
    flow_trend_label: str
    persist_bars: int
    flow_accum: float
    flow_dist: float
    is_dist_warning: bool  # flow_dist >= 70
    rvol5: float
    mode_tag: str  # "ESTABLISHED", "EMERGING_G1", "EMERGING_G2", "BOTH"
    bii: float  # Banker Intensity Index (0-100)
    trace: List[str]
    data_ok: bool
    params_hash: str


@dataclass
class MCDXRadarOutput:
    mode: str
    strength_tier: str
    as_of: str
    total_scanned: int
    qualified_count: int
    excluded_data_ok_false: int
    excluded_low_adtv: int
    candidates: List[MCDXCandidate]
    params_hash: str
    next_step_recommendation: str = "Chạy WFE setup scan (Structure+VPA+Policy) trên top N để ra kế hoạch tranche."
    disclaimer: str = STANDARD_MCDX_DISCLAIMER

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "strength_tier": self.strength_tier,
            "as_of": self.as_of,
            "total_scanned": self.total_scanned,
            "qualified_count": self.qualified_count,
            "excluded_data_ok_false": self.excluded_data_ok_false,
            "excluded_low_adtv": self.excluded_low_adtv,
            "candidates": [asdict(c) for c in self.candidates],
            "params_hash": self.params_hash,
            "next_step_recommendation": self.next_step_recommendation,
            "disclaimer": self.disclaimer
        }


def get_flow_trend_label(val: float) -> str:
    """Classifies flow_trend into standard label."""
    if val <= 0.0:
        return "Vắng bóng"
    elif val < 25.0:
        return "Bắt đầu gom"
    elif val < 50.0:
        return "Kiểm soát"
    else:
        return "Tiền to bùng nổ"


def calculate_linear_slope(series: List[float]) -> float:
    """Calculates slope over a short numeric series."""
    if len(series) < 2:
        return 0.0
    x = np.arange(len(series))
    y = np.array(series, dtype=float)
    x_mean = np.mean(x)
    y_mean = np.mean(y)
    denom = np.sum((x - x_mean) ** 2)
    if denom == 0:
        return 0.0
    slope = np.sum((x - x_mean) * (y - y_mean)) / denom
    return float(slope)


class MCDXFlowRadar:
    """
    SKILL_9 Engine: Scans and ranks stocks based on Institutional Flow signatures.
    """

    def __init__(
        self,
        config: Optional[MCDXRadarConfig] = None,
        kill_switch: Optional[KillSwitchManager] = None
    ):
        self.config = config or DEFAULT_REGISTRY.mcdx_radar
        self.kill_switch = kill_switch or KillSwitchManager()
        self.flow_engine = FlowEngine(DEFAULT_REGISTRY.flow)

    @property
    def params_hash(self) -> str:
        return self.config.params_hash

    def evaluate_symbol(
        self,
        symbol: str,
        bars: List[MarketBar],
        adtv20_bil: float,
        mode: str = "both",
        strength_tier: str = "strong",
        threshold_mode: str = "absolute"
    ) -> Optional[MCDXCandidate]:
        """Evaluates a single stock against ESTABLISHED and EMERGING rules."""
        cfg = self.config
        p_hash = self.params_hash

        if not bars or len(bars) < 70:
            return None

        n = len(bars)
        curr_price = bars[-1].close

        latest_f_out = self.flow_engine.calculate(bars)
        if not latest_f_out.data_ok:
            return None

        # Compute Flow Engine history across recent 20 bars
        lookback = min(20, n - 55)
        rvols = []
        for i in range(n - lookback, n):
            p_sma = compute_prev_sma20_vol(bars, i)
            rv = (bars[i].volume / p_sma) if p_sma > 0 else 1.0
            rvols.append(rv)

        # Expose trend_history from FlowOutput diagnostics (avoids 21x re-calculation)
        full_trend_hist = latest_f_out.diagnostics.get("trend_history", [])
        if full_trend_hist and len(full_trend_hist) >= lookback:
            flow_trend_hist = full_trend_hist[-lookback:]
        else:
            flow_trend_hist = full_trend_hist if full_trend_hist else [latest_f_out.trend.value or 0.0]

        # Only evaluate accum for last 10 bars for slope10_accum
        flow_accum_hist = []
        for i in range(max(0, n - 10), n):
            if i == n - 1:
                flow_accum_hist.append(latest_f_out.accum.value if latest_f_out.accum.value is not None else 0.0)
            else:
                sub_f = self.flow_engine.calculate(bars[:i + 1])
                flow_accum_hist.append(sub_f.accum.value if sub_f.accum.value is not None else 0.0)

        curr_trend = latest_f_out.trend.value if latest_f_out.trend.value is not None else 0.0
        curr_accum = latest_f_out.accum.value if latest_f_out.accum.value is not None else 0.0
        curr_dist = latest_f_out.dist.value if latest_f_out.dist.value is not None else 0.0
        trend_collapse = latest_f_out.trend_collapse_warning

        # SMA5 RVol
        sma5_rvol = float(np.mean(rvols[-5:])) if len(rvols) >= 5 else rvols[-1]

        # Persistence: number of bars in last 5 where flow_trend >= 25
        last5_trends = flow_trend_hist[-5:]
        persist_bars = sum(1 for t in last5_trends if t >= cfg.persist_threshold)

        # dv_contr: SMA5(down_vol) / SMA20(down_vol)
        down_vols = [
            bars[i].volume if (i > 0 and bars[i].close < bars[i - 1].close) else 0.0
            for i in range(n)
        ]
        sma5_dv = sum(down_vols[-5:]) / 5.0
        sma20_dv = sum(down_vols[-20:]) / 20.0
        dv_contr_ratio = (sma5_dv / sma20_dv) if sma20_dv > 0 else (0.0 if sma5_dv == 0 else 1.0)

        # obv_div from diagnostics
        raw_obv_div = latest_f_out.diagnostics.get("obv_div_pos", 0.0)
        obv_div_normalized = raw_obv_div / 100.0 if raw_obv_div > 1.0 else raw_obv_div

        # Slopes
        slope5_trend = calculate_linear_slope(flow_trend_hist[-5:])
        slope10_accum = calculate_linear_slope(flow_accum_hist[-10:])

        # 20-bar price compression range
        highs_20 = [b.high for b in bars[-20:]]
        lows_20 = [b.low for b in bars[-20:]]
        min_l20 = min(lows_20) if lows_20 else 1.0
        max_h20 = max(highs_20) if highs_20 else 1.0
        compression_range = (max_h20 - min_l20) / min_l20 if min_l20 > 0 else 1.0

        # Trace details
        trace: List[str] = []
        is_established = False
        is_emerging_g1 = False
        is_emerging_g2 = False

        # --- 1. EVALUATE ESTABLISHED (E1 - E4) ---
        tier_thresh = cfg.tier_control_threshold if strength_tier == "control" else cfg.tier_strong_threshold
        e1 = curr_trend >= tier_thresh
        e2 = persist_bars >= cfg.persist_min_bars

        # E3: Dual-level check. Normal: sma5_rvol >= 1.10. No Supply context (biên độ nén <= 10% & bán cạn dv_contr <= 0.50): cho phép sma5_rvol >= 0.70
        is_no_supply_context = (compression_range <= 0.10) and (dv_contr_ratio <= 0.50)
        e3_thresh = getattr(cfg, "sma5_rvol_no_supply_min", 0.70) if is_no_supply_context else cfg.sma5_rvol_min
        e3 = sma5_rvol >= e3_thresh
        e4 = (curr_dist <= cfg.flow_dist_max_pct) and (not trend_collapse)

        # Limit-day guard: if >= 2/3 of flow_trend increase came from a single limit-day bar in last 5
        limit_day_spike = False
        trend_5d_delta = max(0.1, curr_trend - flow_trend_hist[-min(5, len(flow_trend_hist))])
        for idx in range(max(1, n - 5), n):
            if bars[idx].is_limit_day:
                hist_idx = idx - (n - len(flow_trend_hist))
                if hist_idx > 0 and hist_idx < len(flow_trend_hist):
                    single_bar_delta = max(0.0, flow_trend_hist[hist_idx] - flow_trend_hist[hist_idx - 1])
                    if single_bar_delta >= (2.0 / 3.0) * trend_5d_delta:
                        limit_day_spike = True
                        break

        if e1 and e2 and e3 and e4 and (not limit_day_spike):
            is_established = True
            e3_note = f" (No Supply context: >={e3_thresh:.2f})" if is_no_supply_context else ""
            trace.append(
                f"ESTABLISHED: E1 (trend={curr_trend:.1f}>={tier_thresh}), "
                f"E2 (persist={persist_bars}/5>={cfg.persist_min_bars}), "
                f"E3 (sma5_rvol={sma5_rvol:.2f}>={e3_thresh:.2f}{e3_note}), "
                f"E4 (dist={curr_dist:.1f}<={cfg.flow_dist_max_pct}, collapse={trend_collapse})"
            )
        elif limit_day_spike:
            trace.append("ESTABLISHED REJECTED: Tăng đột biến >= 2/3 do phiên trần (limit-day guard).")

        # --- 2. EVALUATE EMERGING (G1 OR G2) ---
        # G1: Flow turn
        # flow_trend cuts above 15 at latest bar, after <= 15 in >= 8/10 prior bars
        if len(flow_trend_hist) >= 11:
            prior_10_le15 = sum(1 for t in flow_trend_hist[-11:-1] if t <= cfg.g1_turn_threshold)
            g1_cut = (curr_trend >= cfg.g1_turn_threshold) and (prior_10_le15 >= cfg.g1_prior_bars_le15)
            g1_confirmed = (flow_trend_hist[-2] >= cfg.g1_turn_threshold or curr_trend > flow_trend_hist[-2])
            g1_vol_slope = (slope5_trend > 0) and (sma5_rvol >= cfg.g1_sma5_rvol_min)

            if g1_cut and g1_confirmed and g1_vol_slope and (curr_dist < cfg.g_exclude_flow_dist_max_pct):
                is_emerging_g1 = True
                trace.append(
                    f"EMERGING G1 (Flow Turn): trend={curr_trend:.1f}>=15 (sau {prior_10_le15}/10 phiên <=15), "
                    f"slope5={slope5_trend:.2f}>0, sma5_rvol={sma5_rvol:.2f}>={cfg.g1_sma5_rvol_min}"
                )

        # G2: Stealth Accumulation
        # Threshold handling: absolute vs percentile
        accum_threshold = cfg.g2_flow_accum_min_pct if threshold_mode == "percentile" else 30.0
        g2_cond1 = (curr_trend < cfg.g2_flow_trend_max) and (curr_accum >= accum_threshold) and (slope10_accum >= 0)
        g2_cond2 = (dv_contr_ratio <= cfg.g2_dv_contr_ratio_max)
        g2_cond3 = (obv_div_normalized >= cfg.g2_obv_div_min) and (compression_range <= cfg.g2_compression_range_max)
        g2_not_dist = curr_dist < cfg.g_exclude_flow_dist_max_pct

        if g2_cond1 and g2_cond2 and g2_cond3 and g2_not_dist:
            is_emerging_g2 = True
            trace.append(
                f"EMERGING G2 (Gom bí mật): trend={curr_trend:.1f}<25, accum={curr_accum:.1f}>={accum_threshold}, "
                f"slope10_accum={slope10_accum:.2f}>=0, dv_contr={dv_contr_ratio:.2f}<=0.75, "
                f"obv_div={obv_div_normalized:.2f}>=0.15, nén={compression_range*100:.1f}%<=8%"
            )
        elif g2_cond1 and not g2_not_dist:
            trace.append(f"EMERGING G2 REJECTED: Phân phối cao flow_dist={curr_dist:.1f} >= 50 (Bounce phân phối).")

        # Determine mode eligibility
        req_mode = mode.lower()
        qualified = False
        mode_tag = "NONE"

        if is_established and (is_emerging_g1 or is_emerging_g2):
            mode_tag = "BOTH"
            qualified = (req_mode in ("both", "established", "emerging"))
        elif is_established:
            mode_tag = "ESTABLISHED"
            qualified = (req_mode in ("both", "established"))
        elif is_emerging_g1:
            mode_tag = "EMERGING_G1"
            qualified = (req_mode in ("both", "emerging"))
        elif is_emerging_g2:
            mode_tag = "EMERGING_G2"
            qualified = (req_mode in ("both", "emerging"))

        if not qualified:
            return None

        # --- 3. COMPUTE BANKER INTENSITY INDEX (BII) ---
        pct_rvol5 = min(100.0, (sma5_rvol / 2.0) * 100.0)
        persist_score = (persist_bars / 5.0) * 100.0

        bii_est = (
            cfg.w_bii_est_trend * curr_trend
            + cfg.w_bii_est_persist * persist_score
            + cfg.w_bii_est_rvol5 * pct_rvol5
            + cfg.w_bii_est_accum * curr_accum
            - cfg.w_bii_est_dist * curr_dist
        )
        bii_est = max(0.0, min(100.0, bii_est))

        pct_slope = min(100.0, max(0.0, slope10_accum * 10.0 + 50.0))
        pct_dv = min(100.0, max(0.0, (1.0 - dv_contr_ratio) * 100.0))
        freshness = cfg.bii_freshness_bonus if is_emerging_g1 else 0.0

        bii_emg = (
            cfg.w_bii_emg_accum * curr_accum
            + cfg.w_bii_emg_slope * pct_slope
            + cfg.w_bii_emg_dv * pct_dv
            + cfg.w_bii_emg_obv * (obv_div_normalized * 100.0)
            - cfg.w_bii_emg_dist * curr_dist
            + freshness
        )
        bii_emg = max(0.0, min(100.0, bii_emg))

        if mode_tag == "BOTH":
            bii = max(bii_est, bii_emg)
        elif mode_tag == "ESTABLISHED":
            bii = bii_est
        else:
            bii = bii_emg

        is_dist_warn = curr_dist >= 70.0
        if is_dist_warn:
            trace.append(f"[CẢNH BÁO PHÂN PHỐI] flow_dist={curr_dist:.1f} >= 70.0!")

        return MCDXCandidate(
            symbol=symbol,
            current_price=round(curr_price, 2),
            adtv20_bil=round(adtv20_bil, 2),
            flow_trend=round(curr_trend, 1),
            flow_trend_label=get_flow_trend_label(curr_trend),
            persist_bars=persist_bars,
            flow_accum=round(curr_accum, 1),
            flow_dist=round(curr_dist, 1),
            is_dist_warning=is_dist_warn,
            rvol5=round(sma5_rvol, 2),
            mode_tag=mode_tag,
            bii=round(bii, 1),
            trace=trace,
            data_ok=True,
            params_hash=p_hash
        )

    def scan_radar(
        self,
        candles_by_symbol: Dict[str, List[Dict[str, Any]]],
        mode: str = "both",
        strength_tier: str = "strong",
        min_adtv_billion: float = 15.0,
        top_n: int = 20,
        as_of: str = "last_close"
    ) -> MCDXRadarOutput:
        """
        Scans universe against MCDX Flow Radar criteria.
        Refuses execution if kill-switch flow_mode == 'off'.
        """
        if self.kill_switch.is_flow_off:
            raise RuntimeError(
                "MCDX Flow Radar từ chối thực thi: Flow Engine đang ở trạng thái KILL-SWITCH (flow_mode='off'). "
                "Hệ thống hiện đang thoái hóa an toàn về Structure + VPA Engine."
            )

        candidates: List[MCDXCandidate] = []
        ex_data_ok = 0
        ex_low_adtv = 0
        total_scanned = len(candles_by_symbol)

        for sym, candles in candles_by_symbol.items():
            if not candles or len(candles) < 70:
                ex_data_ok += 1
                continue

            # Convert raw candles to MarketBars
            bars: List[MarketBar] = []
            for c in candles:
                bars.append(MarketBar(
                    date=str(c.get("date", "")),
                    open=float(c.get("open", 0.0)),
                    high=float(c.get("high", 0.0)),
                    low=float(c.get("low", 0.0)),
                    close=float(c.get("close", 0.0)),
                    volume=float(c.get("volume", 0.0)),
                    is_limit_day=bool(c.get("is_limit_day", False)),
                    is_ex_date=bool(c.get("is_ex_date", False))
                ))

            # ADTV 20
            prev_sma = compute_prev_sma20_vol(bars, len(bars) - 1)
            adtv_bil = (prev_sma * bars[-1].close) / 1e6

            if adtv_bil < min_adtv_billion:
                ex_low_adtv += 1
                continue

            cand = self.evaluate_symbol(
                symbol=sym,
                bars=bars,
                adtv20_bil=adtv_bil,
                mode=mode,
                strength_tier=strength_tier
            )
            if cand is not None:
                candidates.append(cand)

        # Sort by BII descending
        candidates.sort(key=lambda x: x.bii, reverse=True)
        top_candidates = candidates[:top_n]

        return MCDXRadarOutput(
            mode=mode,
            strength_tier=strength_tier,
            as_of=as_of,
            total_scanned=total_scanned,
            qualified_count=len(candidates),
            excluded_data_ok_false=ex_data_ok,
            excluded_low_adtv=ex_low_adtv,
            candidates=top_candidates,
            params_hash=self.params_hash,
            next_step_recommendation="Chạy WFE setup scan (Structure+VPA+Policy) trên top N để ra kế hoạch tranche.",
            disclaimer=STANDARD_MCDX_DISCLAIMER
        )
