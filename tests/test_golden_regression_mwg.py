"""
Golden-File Regression Case MWG 09/2026 (Definition of Done #5):
Chuỗi sự kiện hoàn chỉnh: Box TR -> Minor SOS (CP >= 66%) -> Confluence xác suất -> Tranche Plan -> JSON Schema L5.
"""

import pytest
import json
from wfe.scanner import WFEScanner
from wfe.output.schema import LLMRuleValidator


def build_mwg_09_2026_candles() -> list:
    """
    Constructs realistic 130-bar series for MWG forming an accumulation box:
    - Bars 0..80: Base range 62.0 to 70.0 (TR_Low=62, TR_Mid=66, TR_High=70)
    - Bar 85: Minor SOS breaking above TR_Mid with high volume (RVol=1.6) and high CP (0.80)
    - Bars 86..100: Retest / BU / LPS pullback at 66.5 with drying volume (RVol=0.60)
    - Bars 101..125: Healthy consolidation maintaining structure
    """
    candles = []
    base_price = 65.0

    for i in range(125):
        date_str = f"2026-09-{i+1:03d}"
        if i < 85:
            # Inside trading range 62.0 - 70.0
            o = 63.0 + (i % 8) * 0.8
            h = min(70.0, o + 1.5)
            l = max(62.0, o - 1.2)
            c = (h + l) / 2.0
            v = 1500000.0 + (i % 5) * 100000.0
        elif i == 85:
            # Minor SOS: strong green bar above TR_Mid (66.0)
            o = 65.5
            l = 65.2
            h = 68.5
            c = 68.2  # CP = (68.2 - 65.2) / (68.5 - 65.2) = 3.0 / 3.3 = 0.909 >= 0.66
            v = 3500000.0  # RVol > 1.5
        elif 86 <= i <= 95:
            # Pullback BU / LPS: holding above TR_Mid (66.0) with low vol
            o = 67.0 - (i - 86) * 0.08
            h = o + 0.6
            l = max(66.2, o - 0.4)
            c = (h + l) / 2.0
            v = 800000.0  # RVol dry-up ~ 0.50
        else:
            # Steady support holding LPS
            o = 66.5 + (i - 96) * 0.05
            h = o + 0.8
            l = o - 0.3
            c = o + 0.4
            v = 1100000.0

        candles.append({
            "date": date_str,
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": float(v)
        })

    return candles


def test_mwg_09_2026_golden_pipeline():
    """Run full end-to-end regression test on MWG 09/2026 case."""
    scanner = WFEScanner()
    candles = build_mwg_09_2026_candles()

    output = scanner.analyze_symbol(
        symbol="MWG",
        raw_candles=candles,
        exchange="HOSE",
        sector="Bán lẻ"
    )

    # 1. Verify schema completeness
    assert output.schema_version == "3.0.0"
    assert output.symbol == "MWG"
    assert output.flow is not None
    assert output.structure is not None
    assert output.vpa is not None
    assert output.policy is not None

    # 2. Verify Structure detected the box and events
    assert output.structure.data_ok is True
    assert output.structure.box_id.startswith("BOX_")
    events = output.structure.events
    assert len(events) > 0

    has_minor_sos = any(e["event_type"] == "MINOR_SOS" for e in events)
    assert has_minor_sos, "Minor SOS event was not identified!"

    # 3. Verify Policy & Expectancy
    policy = output.policy
    assert policy.data_ok is True
    assert policy.p_success >= 0.45
    assert policy.ev_r > 0.0

    # 4. Verify Tranche Plans exist
    assert len(policy.tranche_plans) == 3
    t1_plan = next(t for t in policy.tranche_plans if t["tranche_id"] == "T1_EVENT_CONFIRM")
    assert t1_plan is not None

    # 5. Verify Traces are rich and detailed
    assert len(output.trace) >= 3
    trace_text = "\n".join(output.trace)
    assert "Regime:" in trace_text
    assert "Feature Row:" in trace_text
    assert "Sizing:" in trace_text

    # 6. Verify LLM Rules Validator on mock report
    mock_llm_report = f"""
# Báo Cáo Phân Tích WFE V3.0 - MWG
Mã MWG được hệ thống xác nhận cấu trúc Trading Range với p_success = {policy.p_success} và EV = {policy.ev_r}R.
Dựa vào trace hệ thống: {output.trace[1]}.
Bằng chứng phản bác: {output.counter_evidence}
Tuyên bố miễn trừ trách nhiệm (Disclaimer): {output.disclaimer}
    """

    is_valid, violations = LLMRuleValidator.validate(mock_llm_report, output)
    assert is_valid, f"LLM report validation failed: {violations}"

    # 7. Verify JSON serializability
    output_json = json.dumps(output.to_dict(), indent=2)
    assert len(output_json) > 500
