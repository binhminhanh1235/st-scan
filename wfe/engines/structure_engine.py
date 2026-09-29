"""
WFE L1 — STRUCTURE ENGINE (Wyckoff)
Architecture Contract:
1. Độc lập tuyệt đối: không import Flow hay Volume Engine.
2. Vai trò: bản đồ & mức giá (entry/stop/target/invalidation), không tự ra quyết định.
3. Xuất TR boxes, stationarity, freeze box, quantitative events, levels, phase probabilities.
4. Không in từ ngữ dự báo.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import hashlib
from wfe.config.registry import StructureEngineConfig, compute_params_hash
from wfe.data.pit_feed import MarketBar, compute_prev_sma20_vol


@dataclass
class QuantitativeEvent:
    event_id: str
    event_type: str  # "SPRING", "TEST", "MINOR_SOS", "SOS", "BU_LPS", "UT_UTAD", "SOW", "LPSY"
    bar_index: int
    price: float
    low: float
    high: float
    event_low: Optional[float] = None
    rvol_est: Optional[float] = None
    cp_est: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BoxLevels:
    box_id: str
    tr_low: float
    tr_mid: float
    tr_high: float
    drift_1: float
    drift_2: float
    is_box_unstable: bool


@dataclass
class PriceLevels:
    tr_low: float
    tr_mid: float
    tr_high: float
    event_low: Optional[float]
    t1: Optional[float]
    major_supply: float
    t2: Optional[float]
    target2_supply_capped: bool
    t1_source: str
    t1_valid: bool = True
    target_tag: str = "[NORMAL]"


@dataclass
class StructureOutput:
    box_id: str
    levels: PriceLevels
    frozen_levels: Dict[str, float]
    is_box_unstable: bool
    phase_prob: Dict[str, float]  # Numerical probability distribution: {"A": p, "B": p, "C": p, "D": p, "E": p}
    events: List[QuantitativeEvent]
    active_setup: Optional[str]  # "TEST_SPRING_PHASE_C", "BU_LPS_PHASE_D", None
    data_ok: bool
    params_hash: str
    diagnostics: Dict[str, Any] = field(default_factory=dict)


class StructureEngine:
    """Structure Engine analyzes Wyckoff Trading Range, events, levels, and phases."""

    def __init__(self, config: Optional[StructureEngineConfig] = None):
        self.config = config or StructureEngineConfig()

    @property
    def params_hash(self) -> str:
        return self.config.params_hash

    def calculate(
        self,
        bars: List[MarketBar],
        frozen_snapshot: Optional[Dict[str, float]] = None
    ) -> StructureOutput:
        cfg = self.config
        p_hash = self.params_hash

        if not bars or len(bars) < 70:
            none_levels = PriceLevels(
                tr_low=0.0, tr_mid=0.0, tr_high=0.0,
                event_low=None, t1=None, major_supply=0.0,
                t2=None, target2_supply_capped=False, t1_source="NONE"
            )
            return StructureOutput(
                box_id="NONE",
                levels=none_levels,
                frozen_levels={},
                is_box_unstable=True,
                phase_prob={"A": 0.2, "B": 0.2, "C": 0.2, "D": 0.2, "E": 0.2},
                events=[],
                active_setup=None,
                data_ok=False,
                params_hash=p_hash,
                diagnostics={"reason": "insufficient_bars"}
            )

        n = len(bars)
        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        curr_price = closes[-1]

        # 1. Trading Range & Stationarity over 3 rolling windows
        # Ensure we have enough bars for windows: -100 to -15
        p_start = max(0, n + cfg.tr_primary_start)
        p_end = max(1, n + cfg.tr_primary_end)
        s1_start = max(0, n + cfg.tr_shift1_start)
        s1_end = max(1, n + cfg.tr_shift1_end)
        s2_start = max(0, n + cfg.tr_shift2_start)
        s2_end = max(1, n + cfg.tr_shift2_end)

        tr_p_high = max(closes[p_start:p_end]) if p_end > p_start else max(closes)
        tr_p_low = min(closes[p_start:p_end]) if p_end > p_start else min(closes)

        tr_s1_high = max(closes[s1_start:s1_end]) if s1_end > s1_start else tr_p_high
        tr_s1_low = min(closes[s1_start:s1_end]) if s1_end > s1_start else tr_p_low

        tr_s2_high = max(closes[s2_start:s2_end]) if s2_end > s2_start else tr_p_high
        tr_s2_low = min(closes[s2_start:s2_end]) if s2_end > s2_start else tr_p_low

        drift_high1 = abs(tr_p_high - tr_s1_high) / tr_p_high if tr_p_high > 0 else 0.0
        drift_high2 = abs(tr_p_high - tr_s2_high) / tr_p_high if tr_p_high > 0 else 0.0
        drift_low1 = abs(tr_p_low - tr_s1_low) / tr_p_low if tr_p_low > 0 else 0.0
        drift_low2 = abs(tr_p_low - tr_s2_low) / tr_p_low if tr_p_low > 0 else 0.0

        max_drift = max(drift_high1, drift_high2, drift_low1, drift_low2)
        is_box_unstable = max_drift > cfg.stationarity_tolerance

        tr_high = round(tr_p_high, 2)
        tr_low = round(tr_p_low, 2)
        tr_mid = round((tr_high + tr_low) / 2.0, 2)

        # Generate unique box_id based on levels and dates
        win_dates = f"{bars[p_start].date} -> {bars[p_end-1].date}"
        box_seed = f"{tr_low}_{tr_high}_{win_dates}"
        box_id = f"BOX_{hashlib.md5(box_seed.encode('utf-8')).hexdigest()[:8]}"

        stationarity_trace = (
            f"Stationarity Trace: W_primary=[{p_start}:{p_end}] (TR_H={tr_p_high:.2f}, TR_L={tr_p_low:.2f}), "
            f"W_shift1=[{s1_start}:{s1_end}] (TR_H={tr_s1_high:.2f}, TR_L={tr_s1_low:.2f}), "
            f"W_shift2=[{s2_start}:{s2_end}] (TR_H={tr_s2_high:.2f}, TR_L={tr_s2_low:.2f}) -> "
            f"drift_H1={drift_high1*100:.1f}%, drift_H2={drift_high2*100:.1f}%, max_drift={max_drift*100:.1f}% "
            f"{'>' if is_box_unstable else '<='} {cfg.stationarity_tolerance*100:.1f}% -> "
            f"{'flag: [BOX_UNSTABLE], T2=None' if is_box_unstable else 'STABLE'}"
        )

        # Frozen snapshot handling
        frozen_levels = frozen_snapshot or {
            "box_id": box_id,
            "window_dates": win_dates,
            "frozen_at": bars[-1].date,
            "tr_low": tr_low,
            "tr_mid": tr_mid,
            "tr_high": tr_high,
            "is_unstable": 1.0 if is_box_unstable else 0.0
        }

        # 2. Major Supply lookback (up to 130 closed bars excluding current bar)
        sup_lookback = min(cfg.major_supply_lookback, n - 1)
        major_supply = round(max(highs[-sup_lookback - 1:-1]), 2) if sup_lookback > 0 else tr_high

        # 3. Detect Quantitative Events
        events: List[QuantitativeEvent] = []

        # (a) Spring detection in last 30 bars:
        # Closes below tr_low of previous range, then reclaims inside box within <= 5 bars
        spring_event = None
        event_low_val = None
        for i in range(max(1, n - 30), n):
            if closes[i] < tr_low:
                # search forward up to 5 bars for reclaim
                reclaim_idx = None
                for k in range(i + 1, min(n, i + cfg.spring_reclaim_max_bars + 1)):
                    if closes[k] >= tr_low:
                        reclaim_idx = k
                        break
                if reclaim_idx is not None:
                    cluster_low = min(lows[i:reclaim_idx + 1])
                    event_low_val = cluster_low
                    ev_id = f"EV_SPRING_{i}"
                    spring_event = QuantitativeEvent(
                        event_id=ev_id,
                        event_type="SPRING",
                        bar_index=i,
                        price=closes[reclaim_idx],
                        low=cluster_low,
                        high=max(highs[i:reclaim_idx + 1]),
                        event_low=cluster_low,
                        details={"reclaim_bar": reclaim_idx, "bars_under": reclaim_idx - i}
                    )
                    events.append(spring_event)
                    break

        if event_low_val is None:
            # Fallback for event_low: minimum low of range [-25:-5]
            event_low_val = min(lows[-25:-5]) if n >= 25 else tr_low

        # (b) Test of Spring / Terminal Shakeout
        # Test: in 25 bars, Event_Low * 0.995 <= Low <= Event_Low * 1.06
        has_test = False
        test_event = None
        test_start = max(1, n - cfg.test_lookback)
        if spring_event is not None and "reclaim_bar" in spring_event.details:
            test_start = max(test_start, spring_event.details["reclaim_bar"] + 1)
        for i in range(test_start, n):
            if event_low_val * cfg.test_low_ratio_min <= lows[i] <= event_low_val * cfg.test_low_ratio_max:
                has_test = True
                test_event = QuantitativeEvent(
                    event_id=f"EV_TEST_{i}",
                    event_type="TEST",
                    bar_index=i,
                    price=closes[i],
                    low=lows[i],
                    high=highs[i],
                    event_low=event_low_val
                )
                events.append(test_event)

        # (c) Minor SOS in last 40 bars: close > tr_mid, RVol >= 1.25, CP >= 0.66 (exclude doji H==L)
        minor_sos_events = []
        sos_events = []
        for i in range(max(1, n - 40), n):
            spread = highs[i] - lows[i]
            if spread <= 0:
                continue  # exclude flat doji
            cp = (closes[i] - lows[i]) / spread
            prev_sma = compute_prev_sma20_vol(bars, i)
            rvol = (bars[i].volume / prev_sma) if prev_sma > 0 else 1.0

            if closes[i] > tr_mid and rvol >= cfg.minor_sos_rvol_min and cp >= cfg.minor_sos_cp_min:
                m_ev = QuantitativeEvent(
                    event_id=f"EV_MINOR_SOS_{i}",
                    event_type="MINOR_SOS",
                    bar_index=i,
                    price=closes[i],
                    low=lows[i],
                    high=highs[i],
                    rvol_est=round(rvol, 2),
                    cp_est=round(cp, 2)
                )
                minor_sos_events.append(m_ev)
                events.append(m_ev)

            # (d) Full SOS: close > tr_high, RVol >= 1.5
            if closes[i] > tr_high and rvol >= cfg.sos_rvol_min:
                sos_ev = QuantitativeEvent(
                    event_id=f"EV_SOS_{i}",
                    event_type="SOS",
                    bar_index=i,
                    price=closes[i],
                    low=lows[i],
                    high=highs[i],
                    rvol_est=round(rvol, 2),
                    cp_est=round(cp, 2)
                )
                sos_events.append(sos_ev)
                events.append(sos_ev)

        # (e) BU/LPS in Phase D
        bu_lps_event = None
        sos_high = None
        if minor_sos_events or sos_events:
            ref_sos = (sos_events or minor_sos_events)[-1]
            sos_bar_idx = ref_sos.bar_index
            sos_leg_rvols = [
                (bars[k].volume / compute_prev_sma20_vol(bars, k))
                for k in range(sos_bar_idx, min(n, sos_bar_idx + 3))
            ]
            avg_sos_rvol = sum(sos_leg_rvols) / len(sos_leg_rvols) if sos_leg_rvols else 1.5
            sos_high = max(highs[sos_bar_idx:])

            # Check pullback at current bar or recent 5 bars:
            # Low >= tr_mid * 0.99 and >= 1.02 * Event_Low, RVol <= 0.8 * avg_sos_rvol, close >= tr_mid
            curr_prev_sma = compute_prev_sma20_vol(bars, n - 1)
            curr_rvol = (bars[-1].volume / curr_prev_sma) if curr_prev_sma > 0 else 1.0
            if (
                lows[-1] >= tr_mid * cfg.bu_lps_mid_factor
                and lows[-1] >= event_low_val * cfg.bu_lps_event_low_factor
                and curr_rvol <= cfg.bu_lps_rvol_pullback_max * avg_sos_rvol
                and curr_price >= tr_mid
                and curr_price <= (sos_high or tr_high) * 0.99
            ):
                bu_lps_event = QuantitativeEvent(
                    event_id=f"EV_BU_LPS_{n-1}",
                    event_type="BU_LPS",
                    bar_index=n - 1,
                    price=curr_price,
                    low=lows[-1],
                    high=highs[-1],
                    details={"sos_high": sos_high}
                )
                events.append(bu_lps_event)

        # (f) UT / UTAD: High > tr_high, Close < tr_high with rejection
        if n >= 2 and highs[-1] > tr_high and closes[-1] < tr_high:
            events.append(QuantitativeEvent(
                event_id=f"EV_UT_{n-1}",
                event_type="UT_UTAD",
                bar_index=n - 1,
                price=curr_price,
                low=lows[-1],
                high=highs[-1]
            ))

        # (g) SOW: close < tr_mid after being near top
        if n >= 2 and closes[-1] < tr_mid and max(highs[-10:]) >= tr_high * 0.98:
            events.append(QuantitativeEvent(
                event_id=f"EV_SOW_{n-1}",
                event_type="SOW",
                bar_index=n - 1,
                price=curr_price,
                low=lows[-1],
                high=highs[-1]
            ))

        # 4. Determine Active Setup & Target Levels
        active_setup = None
        t1_val = None
        t1_src = "NONE"

        # Check Phase C setup: Test of Spring near event_low
        is_phase_c = (
            event_low_val <= tr_low * 1.02
            and event_low_val <= curr_price <= event_low_val * 1.06
            and min(lows[-4:]) >= event_low_val * 0.995
        )

        # Check Phase D setup: BU / LPS after Minor SOS
        ref_sos_event = (sos_events or minor_sos_events)[-1] if (minor_sos_events or sos_events) else None
        is_phase_d = (
            ref_sos_event is not None
            and ref_sos_event.bar_index < n - 1
            and curr_price >= tr_mid * 0.98
            and curr_price <= max(sos_high or tr_high, tr_high) * 1.005
            and curr_price <= tr_high * 1.03
        )

        if is_phase_d:
            active_setup = "BU_LPS_PHASE_D"
            t1_val = round(sos_high or tr_high, 2)
            t1_src = "SOS_HIGH"
        elif is_phase_c:
            active_setup = "TEST_SPRING_PHASE_C"
            t1_val = tr_mid
            t1_src = "TR_MID"
        else:
            t1_val = tr_mid
            t1_src = "DEFAULT_TR_MID"

        # Target 2 calculation with clamping & supply capping:
        # T2 = max(T1 * 1.15, min(TR_High + 0.5 * (TR_High - TR_Low), 0.98 * Major_Supply))
        # If is_box_unstable or T2 <= T1 -> None
        target2_supply_capped = False
        t2_val: Optional[float] = None

        if not is_box_unstable and t1_val is not None and t1_val > 0:
            measured_move = round(tr_high + cfg.t2_buffer_ratio * (tr_high - tr_low), 2)
            if major_supply and major_supply > tr_high:
                supply_cap = round(cfg.t2_supply_cap_discount * major_supply, 2)
                if measured_move > supply_cap:
                    capped_move = supply_cap
                    target2_supply_capped = True
                else:
                    capped_move = measured_move
            else:
                capped_move = measured_move

            # T2 must offer meaningful margin over T1 (at least 5% above T1)
            if capped_move > t1_val * 1.05:
                t2_val = round(capped_move, 2)
            else:
                t2_val = None

        # --- Patch V3.1: 3.x Target validity & level promotion (as-of validity) ---
        t1_valid = (t1_val is not None) and (t1_val > curr_price * 1.00)
        target_tag = "[NORMAL]"
        if not t1_valid:
            pivot_cands = [h for h in highs[-60:] if h > curr_price * 1.02]
            candidates = [x for x in [t2_val, major_supply * 0.98, (min(pivot_cands) if pivot_cands else None)] if x and x > curr_price * 1.02]
            if candidates:
                t1_val = round(min(candidates), 2)
                t1_valid = True
                target_tag = "[TARGET_PROMOTED]"
                # T2 always > T1 after promotion if box is stable
                if not is_box_unstable:
                    higher_cands = [x for x in [major_supply * 0.98, (max(pivot_cands) if pivot_cands else None)] if x and x > t1_val * 1.05]
                    t2_val = round(min(higher_cands), 2) if higher_cands else None
                else:
                    t2_val = None
            else:
                t1_val = None
                t1_valid = False
                target_tag = "[TARGET_EXHAUSTED]"
                t2_val = None

        # 5. Phase Estimator (Probability distribution across A, B, C, D, E)
        # Based on numerical features (box position, event detections)
        prob_dist = {"A": 0.15, "B": 0.25, "C": 0.20, "D": 0.25, "E": 0.15}
        if is_phase_d:
            prob_dist = {"A": 0.05, "B": 0.15, "C": 0.15, "D": 0.55, "E": 0.10}
        elif is_phase_c:
            prob_dist = {"A": 0.10, "B": 0.20, "C": 0.50, "D": 0.15, "E": 0.05}
        elif curr_price > tr_high:
            prob_dist = {"A": 0.05, "B": 0.05, "C": 0.10, "D": 0.30, "E": 0.50}
        elif curr_price < tr_low:
            prob_dist = {"A": 0.35, "B": 0.25, "C": 0.25, "D": 0.10, "E": 0.05}

        levels = PriceLevels(
            tr_low=tr_low,
            tr_mid=tr_mid,
            tr_high=tr_high,
            event_low=round(event_low_val, 2) if event_low_val is not None else None,
            t1=t1_val,
            major_supply=major_supply,
            t2=t2_val,
            target2_supply_capped=target2_supply_capped,
            t1_source=t1_src,
            t1_valid=t1_valid,
            target_tag=target_tag
        )

        return StructureOutput(
            box_id=box_id,
            levels=levels,
            frozen_levels=frozen_levels,
            is_box_unstable=is_box_unstable,
            phase_prob=prob_dist,
            events=events,
            active_setup=active_setup,
            data_ok=True,
            params_hash=p_hash,
            diagnostics={
                "max_drift": round(max_drift, 4),
                "tr_p_high": tr_p_high,
                "tr_p_low": tr_p_low,
                "events_count": len(events),
                "stationarity_trace": stationarity_trace
            }
        )
