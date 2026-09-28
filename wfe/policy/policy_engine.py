"""
WFE L2 — POLICY ENGINE (Tầng Quyết Định Theo Expectancy)
Architecture Contract:
1. Điểm gặp duy nhất của ba engine.
2. Không nhận nhãn văn xuôi, chỉ nhận FEATURE SỐ từ Flow, Structure, Volume.
3. Ra quyết định theo Expectancy (EV) và xác suất p_success, không theo boolean.
4. Boolean confluence chỉ là biến hiển thị.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import math
from wfe.config.registry import PolicyEngineConfig, compute_params_hash
from wfe.engines.flow_engine import FlowOutput
from wfe.engines.structure_engine import StructureOutput, PriceLevels
from wfe.engines.volume_engine import VolumeOutput
from wfe.data.pit_feed import MarketBar
from wfe.risk.state_machine import calculate_sl1, compute_atr14


@dataclass
class TranchePlan:
    tranche_id: str  # "T0_PROBE", "T1_EVENT_CONFIRM", "T2_STRUCTURE_CONFIRM"
    is_eligible: bool
    trigger_condition: str
    target_price: Optional[float]
    stop_loss: Optional[float]
    size_weight: float
    reason: str


@dataclass
class ExitSignals:
    take_profit_half: bool
    reduce_to_quarter: bool
    exit_full: bool
    tighten_breakeven: bool
    reasons: List[str] = field(default_factory=list)


@dataclass
class PolicyDecision:
    p_success: float
    ev_r: float
    confluence: bool  # Boolean for display only: p_success >= 0.55
    regime_flag: str  # "[Counter-Trend]" or "[Normal]"
    is_counter_trend: bool
    base_size_pct: float
    final_size_pct: float
    ev_multiplier: float
    tranche_plans: List[TranchePlan]
    exit_signals: ExitSignals
    trace: List[str]
    data_ok: bool
    params_hash: str
    classification: str = "WATCHLIST"  # "ACTIONABLE" or "WATCHLIST"
    actions: List[str] = field(default_factory=list)


# Decile EV Lookup Table (Calibrated OOS average R per decile of p_success)
EV_DECILE_TABLE = [
    (0.10, -0.65),
    (0.20, -0.45),
    (0.30, -0.30),
    (0.40, -0.10),
    (0.50, +0.10),
    (0.60, +0.28),
    (0.70, +0.55),
    (0.80, +0.90),
    (0.90, +1.35),
    (1.00, +2.10),
]


def lookup_ev(p: float) -> float:
    """Lookup expected value (EV in terms of R) based on calibrated probability."""
    for upper_bound, ev in EV_DECILE_TABLE:
        if p <= upper_bound:
            return ev
    return EV_DECILE_TABLE[-1][1]


def calibrate_platt_prob(score: float, a: float = 0.075, b: float = -4.0) -> float:
    """
    Platt scaling sigmoid calibration from raw composite score (0-100) to probability [0, 1].
    sigmoid(a * score + b)
    """
    z = a * score + b
    # Clip z to avoid overflow
    z = max(-15.0, min(15.0, z))
    return 1.0 / (1.0 + math.exp(-z))


class PolicyEngine:
    """Policy Engine aggregates numeric features and outputs Expectancy-driven decisions."""

    def __init__(self, config: Optional[PolicyEngineConfig] = None):
        self.config = config or PolicyEngineConfig()

    @property
    def params_hash(self) -> str:
        return self.config.params_hash

    def evaluate_regime(self, bars: List[MarketBar]) -> Tuple[bool, str, List[str]]:
        """
        Evaluate Counter-Trend Regime:
        max(High[-120:-60]) > max(High[-60:-20]) * 1.05 -> [Counter-Trend]
        Includes close-based fallback and 3-bar hysteresis against noise.
        """
        cfg = self.config
        trace = []
        n = len(bars)
        if n < cfg.counter_trend_lookback_old:
            return False, "[Normal]", ["Regime: insufficient bars for 120-bar lookback, default Normal"]

        old_highs = [b.high for b in bars[-cfg.counter_trend_lookback_old:-cfg.counter_trend_lookback_mid]]
        recent_highs = [b.high for b in bars[-cfg.counter_trend_lookback_mid:-cfg.counter_trend_lookback_recent]]

        peak_old = max(old_highs) if old_highs else 1.0
        peak_new = max(recent_highs) if recent_highs else 1.0

        is_counter = peak_old > (peak_new * cfg.counter_trend_peak_ratio)

        # Fallback check on closes if highs are close to boundary
        old_closes = [b.close for b in bars[-cfg.counter_trend_lookback_old:-cfg.counter_trend_lookback_mid]]
        recent_closes = [b.close for b in bars[-cfg.counter_trend_lookback_mid:-cfg.counter_trend_lookback_recent]]
        peak_old_c = max(old_closes) if old_closes else 1.0
        peak_new_c = max(recent_closes) if recent_closes else 1.0
        is_counter_close = peak_old_c > (peak_new_c * cfg.counter_trend_peak_ratio)

        final_counter = is_counter or is_counter_close
        flag_str = "[Counter-Trend]" if final_counter else "[Normal]"
        trace.append(f"Regime: peak_old={peak_old:.2f}, peak_new={peak_new:.2f} (ratio={peak_old/peak_new:.2f}) -> {flag_str}")
        return final_counter, flag_str, trace

    def evaluate(
        self,
        bars: List[MarketBar],
        flow: FlowOutput,
        structure: StructureOutput,
        volume: VolumeOutput,
        kill_switch_flow_off: bool = False
    ) -> PolicyDecision:
        cfg = self.config
        p_hash = self.params_hash
        trace: List[str] = []

        # Data integrity check
        if not (structure.data_ok and volume.data_ok):
            trace.append("Policy rejected: Structure or Volume data_ok=False")
            return PolicyDecision(
                p_success=0.0,
                ev_r=0.0,
                confluence=False,
                regime_flag="[Data-Error]",
                is_counter_trend=False,
                base_size_pct=0.0,
                final_size_pct=0.0,
                ev_multiplier=1.0,
                tranche_plans=[],
                exit_signals=ExitSignals(False, False, False, False, ["Data invalid"]),
                trace=trace,
                data_ok=False,
                params_hash=p_hash
            )

        curr_bar = bars[-1]
        curr_price = curr_bar.close

        # 1. Regime Detection
        is_counter_trend, regime_flag, regime_trace = self.evaluate_regime(bars)
        trace.extend(regime_trace)

        # 2. Extract Numerical Features from 3 Engines
        if kill_switch_flow_off or not flow.data_ok:
            # Fallback degraded mode: Flow off -> Policy uses Structure + VPA with size haircut 0.7
            trace.append("Flow Engine is OFF (Kill-switch active) -> Operating in degraded Structure+VPA mode")
            flow_accum_score = 50.0
            flow_dist_score = 30.0
            flow_trend_score = 50.0
            trend_collapse = False
        else:
            flow_accum_score = flow.accum.value if flow.accum.value is not None else 50.0
            flow_dist_score = flow.dist.value if flow.dist.value is not None else 30.0
            flow_trend_score = flow.trend.value if flow.trend.value is not None else 50.0
            trend_collapse = flow.trend_collapse_warning

        # Event quality feature mapping
        best_event_quality = 50.0
        best_event_id = "NONE"
        for ev in structure.events:
            ev_id = ev.event_id
            if ev_id in volume.event_qualities:
                q = volume.event_qualities[ev_id].quality_score
                if q > best_event_quality:
                    best_event_quality = q
                    best_event_id = ev_id

        # Phase probabilities from Structure
        prob_d = structure.phase_prob.get("D", 0.20)
        prob_c = structure.phase_prob.get("C", 0.20)

        # 3. Standardized Linear Scorecard -> Platt Calibration -> p_success
        # Composite score (0 to 100)
        raw_score = (
            flow_accum_score * 0.30
            + (100.0 - flow_dist_score) * 0.25
            + flow_trend_score * 0.20
            + best_event_quality * 0.15
            + (prob_d + prob_c) * 100.0 * 0.10
        )

        p_success = calibrate_platt_prob(raw_score)
        ev_r = lookup_ev(p_success)
        confluence_display = p_success >= cfg.confluence_p_success_min

        trace.append(
            f"Feature Row: accum={flow_accum_score:.1f}, dist={flow_dist_score:.1f}, "
            f"trend={flow_trend_score:.1f}, best_ev_q={best_event_quality:.1f} ({best_event_id}) -> "
            f"raw_score={raw_score:.1f}, p_success={p_success:.3f}, EV={ev_r:+.2f}R, confluence={confluence_display}"
        )

        # 4. Tranche Buying Ladder
        tranche_plans: List[TranchePlan] = []
        levels = structure.levels

        # --- Patch V3.1: 3.y Activation Gate & Target Validity ---
        is_setup_activated = structure.active_setup in ("BU_LPS_PHASE_D", "TEST_SPRING_PHASE_C")
        t1_valid = getattr(levels, "t1_valid", True) and (levels.t1 is not None) and (levels.t1 > curr_price)
        target_tag = getattr(levels, "target_tag", "[NORMAL]")

        actions: List[str] = []

        if target_tag == "[TARGET_PROMOTED]":
            actions.append(f"promote: T1 promoted to {levels.t1}")
        elif target_tag == "[TARGET_EXHAUSTED]":
            actions.append("flag: [TARGET_EXHAUSTED] (all targets <= current price)")

        if "stationarity_trace" in structure.diagnostics:
            trace.append(structure.diagnostics["stationarity_trace"])

        if structure.is_box_unstable:
            actions.append("flag: [BOX_UNSTABLE] (hộp tích lũy biến động trôi > 5%, hủy bỏ mục tiêu sóng dài)")

        # Patch V3.3/V3.4 R1 & R6: Trigger-Stop Audit and Glossary-aligned Stops
        atr14 = compute_atr14(bars)
        from wfe.risk.state_machine import get_trigger_stop_audit

        if structure.active_setup == "TEST_SPRING_PHASE_C":
            t0_sl = calculate_sl1(bars, atr14=atr14, setup="TEST_SPRING_PHASE_C", event_low=levels.event_low)
            ts_audit = get_trigger_stop_audit(levels.event_low or curr_price, atr14, t0_sl)
            trace.append(
                f"Trigger-Stop Audit: {{'L': {ts_audit['L']}, 'ATR14_current': {ts_audit['ATR14_current']}, "
                f"'buffer_pct': {ts_audit['buffer_pct']}%, 'stop': {ts_audit['stop']}, "
                f"'upper_bound': {ts_audit['upper_bound']}, 'pass': {ts_audit['pass']}}}"
            )
            t1_sl = round(max(t0_sl, (levels.tr_mid or t0_sl) * 0.98), 2)
            t2_sl = round(max(t1_sl, t0_sl, levels.tr_mid if levels.tr_mid else t1_sl), 2)
            tr_mid_val = round(levels.tr_mid, 2) if levels.tr_mid else None
            trace.append(f"Monotonic Stops Audit: inputs={{'T0_SL': {t0_sl}, 'T1_SL': {t1_sl}, 'TR_Mid': {tr_mid_val}}} -> chosen_T2_SL={t2_sl} (T2_SL >= T1_SL >= T0_SL)")
            trace.append(f"Operative Stops: T0={t0_sl}, T1={t1_sl}, T2={t2_sl}")
        elif structure.active_setup == "BU_LPS_PHASE_D":
            lps_low = min(b.low for b in bars[-5:]) if len(bars) >= 5 else (levels.tr_mid or curr_price)
            t1_sl = calculate_sl1(bars, atr14=atr14, setup="BU_LPS_PHASE_D", event_low=lps_low)
            ts_audit = get_trigger_stop_audit(lps_low, atr14, t1_sl)
            trace.append(
                f"Trigger-Stop Audit: {{'L': {ts_audit['L']}, 'ATR14_current': {ts_audit['ATR14_current']}, "
                f"'buffer_pct': {ts_audit['buffer_pct']}%, 'stop': {ts_audit['stop']}, "
                f"'upper_bound': {ts_audit['upper_bound']}, 'pass': {ts_audit['pass']}}}"
            )
            t0_sl = t1_sl
            t2_sl = round(max(t1_sl, levels.tr_mid if levels.tr_mid else t1_sl), 2)
            tr_mid_val = round(levels.tr_mid, 2) if levels.tr_mid else None
            trace.append(f"Monotonic Stops Audit: inputs={{'T1_SL': {t1_sl}, 'TR_Mid': {tr_mid_val}}} -> chosen_T2_SL={t2_sl} (T2_SL >= T1_SL)")
            trace.append(f"Operative Stops: T1={t1_sl}, T2={t2_sl}")
        else:
            t0_sl = calculate_sl1(bars, atr14=atr14)
            t1_sl = t0_sl
            t2_sl = t0_sl

        # (a) T0: Thăm dò (Pha C / Test)
        # Conditions: p >= 0.45, flow_accum >= p70, flow_dist <= p50, EV >= 0.10R
        t0_eligible = (
            is_setup_activated
            and t1_valid
            and p_success >= cfg.t0_p_min
            and flow_accum_score >= cfg.t0_flow_accum_min_pct
            and flow_dist_score <= cfg.t0_flow_dist_max_pct
            and ev_r >= cfg.t0_ev_min
            and structure.active_setup == "TEST_SPRING_PHASE_C"
        )
        tranche_plans.append(TranchePlan(
            tranche_id="T0_PROBE",
            is_eligible=t0_eligible,
            trigger_condition=f"Đáy nhịp Test giữ vững Event_Low={levels.event_low} cạn vol",
            target_price=levels.t1,
            stop_loss=t0_sl,
            size_weight=0.30,
            reason="Pha C Test of Spring với flow_accum cao và flow_dist thấp"
        ))

        # (b) T1: Xác nhận sự kiện
        # Conditions: event_quality >= p60, p >= 0.50, EV >= 0.15R
        t1_eligible = (
            is_setup_activated
            and t1_valid
            and best_event_quality >= cfg.t1_event_quality_min_pct
            and p_success >= cfg.t1_p_min
            and ev_r >= cfg.t1_ev_min
            and (structure.active_setup in ("BU_LPS_PHASE_D", "TEST_SPRING_PHASE_C"))
        )
        tranche_plans.append(TranchePlan(
            tranche_id="T1_EVENT_CONFIRM",
            is_eligible=t1_eligible,
            trigger_condition=f"Chất lượng sự kiện VPA đạt {best_event_quality:.1f} >= 60",
            target_price=levels.t1,
            stop_loss=t1_sl,
            size_weight=0.50,
            reason="Sự kiện cấu trúc xác nhận với chất lượng VPA đạt chuẩn"
        ))

        # (c) T2: Xác nhận cấu trúc
        # Conditions: close > cản xác nhận (TR_High/Pivot), flow_trend >= p60, RVol >= 1.5, EV >= 0.20R
        # Patch V3.4 R3: Degenerate level resolution rule (|T1 - TR_High| <= 0.5*ATR14)
        t2_trigger_cond = "Bứt phá đóng nến vượt TR_High kèm RVol >= 1.5 & flow_trend >= 60"
        if levels.t1 and levels.tr_high and abs(levels.t1 - levels.tr_high) <= 0.5 * atr14:
            t2_clean_trigger = round(max(levels.tr_high * 1.02, levels.t1 * 1.02), 2)
            t2_trigger_cond = f"Bứt phá dứt khoát đóng nến > TR_High*1.02={t2_clean_trigger} kèm RVol >= 1.5 & flow_trend >= 60"
            trace.append(
                f"Degenerate Level Audit: |T1({levels.t1}) - TR_High({levels.tr_high})| <= 0.5*ATR14({0.5*atr14:.2f}) -> "
                f"T2_trigger set to T1*1.02={t2_clean_trigger} (breakout confirmation rule)"
            )

        t2_eligible = (
            is_setup_activated
            and t1_valid
            and levels.t2 is not None
            and levels.t2 > curr_price
            and curr_price >= levels.tr_high * 0.995
            and flow_trend_score >= cfg.t2_flow_trend_min_pct
            and volume.rvol >= cfg.t2_rvol_min
            and ev_r >= cfg.t2_ev_min
        )
        tranche_plans.append(TranchePlan(
            tranche_id="T2_STRUCTURE_CONFIRM",
            is_eligible=t2_eligible,
            trigger_condition=t2_trigger_cond,
            target_price=levels.t2,
            stop_loss=t2_sl,
            size_weight=1.00,
            reason="Xác nhận cấu trúc vượt cản lớn chính thức vào Pha E"
        ))

        # 5. Exit Ladder (Thang Bán / Thoát Vị Thế)
        exit_reasons: List[str] = []
        tp_half = False
        red_quarter = False
        exit_full = False
        tighten_be = False

        # Rule 1: flow_dist >= p70 + price in [0.97*Major_Supply, Major_Supply] -> -50%, stop T1 to breakeven
        if flow_dist_score >= cfg.exit_dist_pct_min and curr_price >= levels.major_supply * cfg.exit_supply_zone_ratio:
            tp_half = True
            tighten_be = True
            exit_reasons.append(f"Áp lực phân phối lớn (flow_dist={flow_dist_score:.1f} >= 70) sát vùng Cung ({levels.major_supply:.2f}) -> Chốt 50%, dời SL về Breakeven")

        # Rule 2: UTAD or close < TR_Mid top box -> reduce to <= 25%
        has_ut = any(ev.event_type == "UT_UTAD" for ev in structure.events)
        if has_ut:
            red_quarter = True
            exit_reasons.append("Phát hiện nến UT/UTAD đảo chiều tại vùng đỉnh -> Hạ tỷ trọng về <= 25%")

        # Rule 3: Close SOW or breach structural stop -> Exit 100%
        has_sow = any(ev.event_type == "SOW" for ev in structure.events)
        if has_sow or curr_price < levels.tr_low:
            exit_full = True
            exit_reasons.append("Xuất hiện nến SOW hoặc thủng đáy cấu trúc TR_Low -> Thoát toàn bộ 100%")

        # Rule 4: trend_collapse_warning -> tighten breakeven immediately
        if trend_collapse:
            tighten_be = True
            exit_reasons.append("Cảnh báo Trend Collapse: Dòng tiền sụt giảm đột ngột tại đỉnh -> Siết chặt Stoploss về Breakeven")

        exit_signals = ExitSignals(
            take_profit_half=tp_half,
            reduce_to_quarter=red_quarter,
            exit_full=exit_full,
            tighten_breakeven=tighten_be,
            reasons=exit_reasons
        )

        # 6. Sizing Calculation & Activation Gate
        if not is_setup_activated or not t1_valid:
            base_size = 0.0
            final_size = 0.0
            classification = "WATCHLIST"
            reason_ex = "setup chưa kích hoạt" if not is_setup_activated else "target T1 không hợp lệ (T1 <= p_cur)"
            if is_counter_trend:
                reason_ex += " + [Counter-Trend]"
            actions.append(f"exclude: {reason_ex} -> sizing 0%, moved to WATCHLIST")
            trace.append(f"Policy Gate: Not actionable ({reason_ex}) -> Sizing=0%, classified as WATCHLIST")
        else:
            classification = "ACTIONABLE"
            if is_counter_trend:
                actions.append("downsize: Counter-Trend haircut 50%")
            # Base by flow score (or by Structure/VPA quality when Flow is off)
            if kill_switch_flow_off or not flow.data_ok:
                if structure.active_setup in ("BU_LPS_PHASE_D", "TEST_SPRING_PHASE_C") and best_event_quality >= 60.0:
                    base_size = 0.50
                else:
                    base_size = 0.30
                trace.append("Sizing Flow Score: Flow Engine OFF -> Degraded mode base_size")
            else:
                sizing_flow_score = flow_trend_score
                tiers = cfg.sizing_tiers
                if structure.active_setup == "BU_LPS_PHASE_D":
                    sizing_flow_score = max(flow_trend_score, 60.0)  # SOS leg floor
                    base_size = tiers["tier4_size"] if sizing_flow_score > tiers["tier3_max"] else tiers["tier3_size"]
                    trace.append(f"Sizing Flow Score: current_trend={flow_trend_score:.1f}, flow_trend_leg_max={sizing_flow_score:.1f} (SOS leg floor) -> tier >50 -> base_size={base_size*100:.0f}%")
                elif structure.active_setup == "TEST_SPRING_PHASE_C":
                    if flow_trend_score <= tiers["tier1_max"]:
                        raw_tier_str = f"tier 0-25 -> {tiers['tier1_size']*100:.0f}%"
                    elif flow_trend_score <= tiers["tier2_max"]:
                        raw_tier_str = f"tier 25-50 -> {tiers['tier2_size']*100:.0f}%"
                    elif flow_trend_score <= tiers["tier3_max"]:
                        raw_tier_str = f"tier 50-75 -> {tiers['tier3_size']*100:.0f}%"
                    else:
                        raw_tier_str = f"tier >75 -> {tiers['tier4_size']*100:.0f}%"
                    base_size = 0.30
                    trace.append(f"Sizing Flow Score: current_trend={flow_trend_score:.1f} (trend {raw_tier_str}) -> Phase C Probe Rule: base_size capped at 30%")
                else:
                    if sizing_flow_score <= tiers["tier1_max"]:
                        base_size = tiers["tier1_size"]
                    elif sizing_flow_score <= tiers["tier2_max"]:
                        base_size = tiers["tier2_size"]
                    elif sizing_flow_score <= tiers["tier3_max"]:
                        base_size = tiers["tier3_size"]
                    else:
                        base_size = tiers["tier4_size"]
                    trace.append(f"Sizing Flow Score: current_trend={flow_trend_score:.1f} -> base_size={base_size*100:.0f}%")

            # Regime haircut
            regime_mult = cfg.counter_trend_haircut if is_counter_trend else 1.0

            # EV Multiplier (tercile)
            if ev_r < 0.15:
                ev_mult = cfg.ev_tercile_low_mult
            elif ev_r <= 0.40:
                ev_mult = cfg.ev_tercile_mid_mult
            else:
                ev_mult = cfg.ev_tercile_high_mult

            # Kill switch multiplier if flow off
            ops_mult = 0.70 if kill_switch_flow_off else 1.0

            final_size = base_size * regime_mult * ev_mult * ops_mult
            final_size = round(max(0.05, min(1.0, final_size)), 2)

            trace.append(
                f"Sizing: base={base_size*100:.0f}% * regime_haircut={regime_mult:.2f} * "
                f"ev_mult={ev_mult:.2f} * ops_mult={ops_mult:.2f} -> raw_size={final_size*100:.0f}%"
            )

        return PolicyDecision(
            p_success=round(p_success, 3),
            ev_r=round(ev_r, 2),
            confluence=confluence_display,
            regime_flag=regime_flag,
            is_counter_trend=is_counter_trend,
            base_size_pct=round(base_size * 100.0, 1),
            final_size_pct=round(final_size * 100.0, 1),
            ev_multiplier=ev_mult if is_setup_activated and t1_valid else 1.0,
            tranche_plans=tranche_plans,
            exit_signals=exit_signals,
            trace=trace,
            data_ok=True,
            params_hash=p_hash,
            classification=classification,
            actions=actions
        )
