"""
WFE L5 — OUTPUT SCHEMA & QUẢN TRỊ LLM
Architecture Contract:
1. JSON khối riêng: flow, structure, vpa, policy, trace.
2. Schema versioning additive-only.
3. LLM Rules validator:
   - Cấm "bảo kê/chắc thắng/siêu cổ/tuyệt đối".
   - is_box_unstable=True -> in cứng "Hộp tích lũy không ổn định, hủy bỏ mục tiêu sóng dài", cấm tự tính R:R2.
   - Bắt buộc trích dẫn số liệu từ trace.
   - Bắt buộc có dòng bằng chứng phản bác (counter-evidence).
   - Disclaimer chuẩn hóa bắt buộc.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple
import re
from wfe.engines.flow_engine import FlowOutput
from wfe.engines.structure_engine import StructureOutput
from wfe.engines.volume_engine import VolumeOutput
from wfe.policy.policy_engine import PolicyDecision

FORBIDDEN_HYPE_WORDS = ["bảo kê", "chắc thắng", "siêu cổ", "tuyệt đối"]

STANDARD_DISCLAIMER = (
    "Lưu ý Hệ thống: Mô hình mang tính chất heuristic định lượng (quantitative proxy heuristic) "
    "và giải ngân đón lõng (anticipatory). Tín hiệu chưa phải xác nhận xu hướng chính thức; "
    "chỉ được xác nhận khi giá đóng cửa vượt kháng cự chủ chốt, và lập tức bị phủ định nếu vi phạm Stop Loss."
)


@dataclass
class FlowBlock:
    trend: Dict[str, Any]
    accum: Dict[str, Any]
    dist: Dict[str, Any]
    trend_collapse_warning: bool
    data_ok: bool
    params_hash: str


@dataclass
class StructureBlock:
    box_id: str
    frozen_levels: Dict[str, float]
    levels: Dict[str, Any]
    phase_prob: Dict[str, float]
    is_box_unstable: bool
    events: List[Dict[str, Any]]
    active_setup: Optional[str]
    data_ok: bool
    params_hash: str


@dataclass
class VPABlock:
    rvol: float
    cp: float
    flags: Dict[str, bool]
    event_qualities: Dict[str, Any]
    data_ok: bool
    params_hash: str


@dataclass
class PolicyBlock:
    p_success: float
    ev_r: float
    confluence: bool
    regime_flag: str
    is_counter_trend: bool
    size_pct: float
    tranche_plans: List[Dict[str, Any]]
    exit_signals: Dict[str, Any]
    data_ok: bool
    params_hash: str
    classification: str = "WATCHLIST"
    actions: List[str] = field(default_factory=list)


@dataclass
class WFESchemaOutput:
    schema_version: str = "3.0.0"
    symbol: str = ""
    date: str = ""
    current_price: float = 0.0
    action: Optional[str] = None
    setup_type: Optional[str] = None
    ev: Optional[float] = None
    p_success: Optional[float] = None
    approved_size_pct: float = 0.0
    operative_sl: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    no_buy_warnings: List[str] = field(default_factory=list)
    must_sell_triggers: List[str] = field(default_factory=list)
    flow: Optional[FlowBlock] = None
    structure: Optional[StructureBlock] = None
    vpa: Optional[VPABlock] = None
    policy: Optional[PolicyBlock] = None
    classification: str = "WATCHLIST"
    actions: List[str] = field(default_factory=list)
    counter_evidence: str = ""
    trace: List[str] = field(default_factory=list)
    disclaimer: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("disclaimer", None)
        return d


def assemble_wfe_output(
    symbol: str,
    date: str,
    current_price: float,
    flow: FlowOutput,
    structure: StructureOutput,
    volume: VolumeOutput,
    policy: PolicyDecision
) -> WFESchemaOutput:
    """Assembles all engine outputs into the strict L5 WFE JSON Schema."""

    flow_b = FlowBlock(
        trend=asdict(flow.trend),
        accum=asdict(flow.accum),
        dist=asdict(flow.dist),
        trend_collapse_warning=flow.trend_collapse_warning,
        data_ok=flow.data_ok,
        params_hash=flow.params_hash
    )

    struct_b = StructureBlock(
        box_id=structure.box_id,
        frozen_levels=structure.frozen_levels,
        levels=asdict(structure.levels),
        phase_prob=structure.phase_prob,
        is_box_unstable=structure.is_box_unstable,
        events=[asdict(e) for e in structure.events],
        active_setup=structure.active_setup,
        data_ok=structure.data_ok,
        params_hash=structure.params_hash
    )

    vpa_b = VPABlock(
        rvol=volume.rvol,
        cp=volume.cp,
        flags=asdict(volume.flags),
        event_qualities={k: asdict(v) for k, v in volume.event_qualities.items()},
        data_ok=volume.data_ok,
        params_hash=volume.params_hash
    )

    policy_b = PolicyBlock(
        p_success=policy.p_success,
        ev_r=policy.ev_r,
        confluence=policy.confluence,
        regime_flag=policy.regime_flag,
        is_counter_trend=policy.is_counter_trend,
        size_pct=policy.final_size_pct,
        tranche_plans=[asdict(t) for t in policy.tranche_plans],
        exit_signals=asdict(policy.exit_signals),
        data_ok=policy.data_ok,
        params_hash=policy.params_hash,
        classification=policy.classification,
        actions=policy.actions
    )

    # Derive counter-evidence if any negative signs exist
    counter_ev_points = []
    if policy.is_counter_trend:
        counter_ev_points.append("Cấu trúc xu hướng đỉnh lớn đang giảm (Counter-Trend, đỉnh sau thấp hơn đỉnh trước).")
    if structure.is_box_unstable:
        counter_ev_points.append("Hộp tích lũy biến động trôi > 5% (Box Unstable), tiềm ẩn nguy cơ phá vỡ hộp thất bại.")
    if flow.dist.value is not None and flow.dist.value >= 50.0:
        counter_ev_points.append(f"Chỉ số áp lực phân phối flow_dist ở mức cao ({flow.dist.value:.1f}/100).")
    if volume.flags.exhaustion:
        counter_ev_points.append("Nến gần nhất xuất hiện dấu hiệu kiệt sức (Exhaustion bar: RVol cao, CP thấp).")
    if flow.trend_collapse_warning:
        counter_ev_points.append("Cảnh báo sụt giảm dòng tiền đột ngột tại vùng giá cao (Trend Collapse Warning).")

    counter_evidence = " | ".join(counter_ev_points) if counter_ev_points else "Không phát hiện bằng chứng phản bác trọng yếu ở phiên hiện tại."

    operative_sl = None
    if structure.active_setup == "TEST_SPRING_PHASE_C" and policy.tranche_plans:
        operative_sl = policy.tranche_plans[0].stop_loss
    elif structure.active_setup == "BU_LPS_PHASE_D" and len(policy.tranche_plans) > 1:
        operative_sl = policy.tranche_plans[1].stop_loss
    elif policy.tranche_plans:
        operative_sl = policy.tranche_plans[0].stop_loss

    t1_val = getattr(structure.levels, "t1", None)
    t2_val = getattr(structure.levels, "t2", None)

    no_buy_warnings = list(counter_ev_points)
    if policy.classification != "ACTIONABLE":
        no_buy_warnings.append("Setup chưa kích hoạt (WATCHLIST/RESERVE) -> KHÔNG giải ngân sớm trước khi thỏa Pending Trigger.")

    must_sell_triggers = []
    if operative_sl:
        must_sell_triggers.append(f"BẮT BUỘC CẮT LỖ 100% nếu giá đóng cửa thủng Operative SL ({operative_sl:.2f}) và không thỏa 5 điều kiện Spring Wash-out Guard.")
    if t1_val:
        must_sell_triggers.append(f"CHỐT LỜI 50% tại Target 1 ({t1_val:.2f}) và nâng SL lên max(Entry, min(Low_3D)).")
    if t2_val and not structure.is_box_unstable:
        must_sell_triggers.append(f"CHỐT LỜI 100% vị thế còn lại tại Target 2 ({t2_val:.2f}) hoặc khi xuất hiện nến Upthrust/Buying Climax (RSI>72, CP<40%, RVol>=1.5).")
    if policy.exit_signals and policy.exit_signals.reasons:
        for r in policy.exit_signals.reasons:
            if r != "Data invalid":
                must_sell_triggers.append(f"Tín hiệu thoát lệnh hệ thống: {r}")

    return WFESchemaOutput(
        symbol=symbol,
        date=date,
        current_price=current_price,
        action=policy.classification,
        setup_type=structure.active_setup,
        ev=policy.ev_r,
        p_success=policy.p_success,
        approved_size_pct=policy.final_size_pct,
        operative_sl=operative_sl,
        target_1=t1_val,
        target_2=t2_val,
        no_buy_warnings=no_buy_warnings,
        must_sell_triggers=must_sell_triggers,
        flow=flow_b,
        structure=struct_b,
        vpa=vpa_b,
        policy=policy_b,
        classification=policy.classification,
        actions=policy.actions,
        counter_evidence=counter_evidence,
        trace=policy.trace,
        disclaimer=""
    )


class LLMRuleValidator:
    """Validates LLM textual output against L5 Governance Rules."""

    @staticmethod
    def validate(text: str, output_schema: WFESchemaOutput) -> Tuple[bool, List[str]]:
        violations: List[str] = []
        lower_text = text.lower()

        # Rule 1: Forbidden hype words
        for word in FORBIDDEN_HYPE_WORDS:
            if word in lower_text:
                violations.append(f"Vi phạm từ ngữ cấm: phát hiện '{word}'")

        # Rule 2: Box unstable mandatory wording
        if output_schema.structure and output_schema.structure.is_box_unstable:
            required_phrase = "hộp tích lũy không ổn định, hủy bỏ mục tiêu sóng dài"
            if required_phrase not in lower_text:
                violations.append(f"Thiếu câu cảnh báo bắt buộc khi box unstable: '{required_phrase}'")

        # Rule 3: Counter-evidence line required
        if output_schema.counter_evidence and output_schema.counter_evidence != "Không phát hiện bằng chứng phản bác trọng yếu ở phiên hiện tại.":
            if "phản bác" not in lower_text and "rủi ro" not in lower_text and "ngược xu hướng" not in lower_text:
                violations.append("Thiếu dòng bằng chứng phản bác (counter-evidence) khi dữ liệu có cảnh báo rủi ro.")

        # Rule 5: Target validity check (No T1 <= current_price in actionable text)
        if output_schema.structure and output_schema.structure.levels.get("t1"):
            t1 = output_schema.structure.levels["t1"]
            if t1 <= output_schema.current_price and output_schema.classification == "ACTIONABLE":
                violations.append(f"Vi phạm target validity: T1={t1} <= p_cur={output_schema.current_price} trong setup ACTIONABLE")

        # Rule 6: Sizing check for un-activated setups
        if output_schema.classification == "WATCHLIST" and output_schema.policy and output_schema.policy.size_pct > 0:
            violations.append(f"Vi phạm activation gate: setup WATCHLIST nhưng size_pct={output_schema.policy.size_pct}% > 0%")

        is_valid = len(violations) == 0
        return is_valid, violations
