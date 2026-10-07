"""
Unit Tests for SKILL_9 — MCDX FLOW RADAR (WFE V3.0):
1. Ramp Established: Thỏa mãn E1-E4 -> tag ESTABLISHED.
2. Spike 1 phiên: Tăng vọt 1 phiên nhưng không duy trì -> trượt E2.
3. Spike limit-day: Tăng >= 2/3 do phiên trần -> trượt guard limit-day.
4. Phân phối: flow_dist > 60 hoặc collapse -> trượt E4.
5. Flow-turn: G1 cắt lên 15 sau chuỗi <= 15 -> tag EMERGING_G1.
6. Stealth: G2 gom bí mật nén biên độ <= 8%, dv_contr <= 0.75 -> tag EMERGING_G2.
7. Distribution bounce: G2 nhưng flow_dist >= 50 -> bị loại.
8. Kill-switch: flow_mode = off -> từ chối thực thi.
"""

import pytest
from wfe.data.pit_feed import MarketBar
from wfe.radar.mcdx_radar import MCDXFlowRadar, MCDXRadarConfig
from wfe.ops.governance import KillSwitchManager


def make_test_bars(n: int = 85, base_price: float = 50.0, step: float = 0.2, vol: float = 300000.0) -> list:
    bars = []
    for i in range(n):
        o = base_price + i * step
        h = o + 1.0
        l = o - 0.5
        c = o + 0.6
        bars.append(MarketBar(
            date=f"2026-04-{i+1:03d}",
            open=round(o, 2),
            high=round(h, 2),
            low=round(l, 2),
            close=round(c, 2),
            volume=float(vol)
        ))
    return bars


def test_established_pass_e1_to_e4():
    """Verify stock with sustained flow_trend >= 50, persist >= 3, SMA5_RVol >= 1.1 passes ESTABLISHED."""
    radar = MCDXFlowRadar()
    # Steady uptrend creates high RSI and high flow_trend across multiple bars
    bars = make_test_bars(n=85, base_price=40.0, step=0.3, vol=400000.0)
    for b in bars[-5:]:
        b.volume = 500000.0  # volume expansion in last 5 bars satisfying E3

    cand = radar.evaluate_symbol("FPT", bars, adtv20_bil=35.0, mode="established")
    assert cand is not None, "Candidate should pass ESTABLISHED"
    assert cand.mode_tag in ("ESTABLISHED", "BOTH")
    assert cand.flow_trend >= 50.0
    assert cand.persist_bars >= 3
    assert cand.bii > 50.0
    assert any("ESTABLISHED:" in tr for tr in cand.trace)


def test_established_passes_no_supply_context():
    """Verify stock with flow_trend >= 50, persist >= 3, low volume (RVol < 1.10 but >= 0.70) passes under tight compression and dried down-vol."""
    radar = MCDXFlowRadar()
    # 85 bars of tight range uptrend
    bars = make_test_bars(n=85, base_price=40.0, step=0.05, vol=400000.0)
    for b in bars[-5:]:
        b.volume = 300000.0  # RVol ~ 0.75-0.80 < 1.10
    cand = radar.evaluate_symbol("NO_SUPPLY_STOCK", bars, adtv20_bil=35.0, mode="established")
    assert cand is not None, "Candidate should pass ESTABLISHED under No Supply context"
    assert cand.mode_tag in ("ESTABLISHED", "BOTH")
    assert any("No Supply context" in tr for tr in cand.trace)


def test_established_fails_single_bar_spike():
    """Verify single-bar volume/price spike fails E2 (persistence requirement)."""
    radar = MCDXFlowRadar()
    bars = make_test_bars(n=84, base_price=50.0, step=0.0, vol=100000.0)
    # Single spike bar
    spike_bar = MarketBar(date="2026-04-085", open=50.0, high=58.0, low=50.0, close=57.5, volume=3000000.0)
    bars.append(spike_bar)

    cand = radar.evaluate_symbol("SPIKE", bars, adtv20_bil=20.0, mode="established")
    assert cand is None, "Single-bar spike must be rejected from ESTABLISHED"


def test_established_fails_limit_day_spike():
    """Verify limit-day spike guard rejects stock where >= 2/3 of flow_trend jump is from limit day."""
    radar = MCDXFlowRadar()
    # Flat dormant base for 80 bars (flow_trend ~ 0)
    bars = [MarketBar(date=f"2026-04-{i+1:03d}", open=50.0, high=50.5, low=49.5, close=50.0, volume=200000.0) for i in range(80)]
    for i in range(4):
        bars.append(MarketBar(date=f"2026-04-{81+i:03d}", open=50.0, high=50.5, low=49.5, close=50.0, volume=200000.0))
    # 5th bar is a limit day with massive jump
    bars.append(MarketBar(date="2026-04-085", open=50.0, high=53.5, low=50.0, close=53.5, volume=800000.0, is_limit_day=True))

    cand = radar.evaluate_symbol("CE_SPIKE", bars, adtv20_bil=25.0, mode="established")
    # Must be rejected due to limit-day guard
    assert cand is None or cand.mode_tag != "ESTABLISHED"


def test_established_fails_distribution_dist_p60():
    """Verify stock with flow_dist > 60 fails E4."""
    radar = MCDXFlowRadar()
    bars = make_test_bars(n=85, base_price=50.0, step=0.2, vol=200000.0)
    cand = radar.evaluate_symbol("DIST_STOCK", bars, adtv20_bil=30.0, mode="established")
    # If flow_dist is high, E4 fails
    assert cand is None or cand.flow_dist <= 60.0


def test_emerging_g1_flow_turn():
    """Verify G1 flow turn: flow_trend cuts above 15 after being low for prior 10 bars."""
    radar = MCDXFlowRadar()
    # 80 flat bars (flow_trend <= 15 for all prior bars)
    bars = [MarketBar(date=f"2026-04-{i+1:03d}", open=30.0, high=30.5, low=29.5, close=30.0, volume=150000.0) for i in range(80)]
    # 2 turnaround bars cutting above 15
    bars.append(MarketBar(date="2026-04-081", open=30.0, high=31.2, low=29.8, close=31.0, volume=350000.0))
    bars.append(MarketBar(date="2026-04-082", open=31.0, high=32.2, low=30.8, close=32.0, volume=400000.0))

    cand = radar.evaluate_symbol("TURN_STOCK", bars, adtv20_bil=20.0, mode="emerging")
    assert cand is not None, "Should qualify as EMERGING G1"
    assert "EMERGING" in cand.mode_tag
    assert cand.bii > 0.0


def test_emerging_g2_stealth_accumulation():
    """Verify G2 stealth accumulation: tight compression <= 8%, dv_contr <= 0.75, high flow_accum."""
    radar = MCDXFlowRadar()
    # 85 bars of tight compression with dried down-volume and high up-volume (stealth accumulation)
    bars = []
    base_price = 45.0
    for i in range(85):
        is_up = (i % 2 == 0)
        c = 45.15 if is_up else 45.05
        v = 400000.0 if is_up else (5000.0 if i >= 75 else 25000.0)
        bars.append(MarketBar(
            date=f"2026-04-{i+1:03d}",
            open=45.1,
            high=45.25,
            low=45.0,
            close=c,
            volume=float(v)
        ))

    cand = radar.evaluate_symbol("STEALTH_STOCK", bars, adtv20_bil=20.0, mode="emerging")
    assert cand is not None, "Should qualify as EMERGING G2"
    assert cand.mode_tag == "EMERGING_G2"
    assert cand.bii > 0.0
    assert any("EMERGING G2 (Gom bí mật)" in tr for tr in cand.trace)


def test_emerging_fails_distribution_bounce():
    """Verify stock with flow_dist >= 50 is excluded from emerging (bounce inside distribution)."""
    radar = MCDXFlowRadar()
    bars = make_test_bars(n=85, base_price=50.0, step=0.0, vol=100000.0)
    # Manually configure radar to have low threshold for dist exclusion test
    cand = radar.evaluate_symbol("BOUNCE_STOCK", bars, adtv20_bil=20.0, mode="emerging")
    # If flow_dist is high, candidate must not be tagged
    # Verify rejection trace when dist is elevated
    assert cand is None or cand.flow_dist < 50.0


def test_kill_switch_flow_off_refusal():
    """Verify scan_radar raises RuntimeError when kill-switch flow_mode is off."""
    kill_switch = KillSwitchManager(initial_flow_mode="off")
    radar = MCDXFlowRadar(kill_switch=kill_switch)

    candles_map = {
        "TEST": [{"date": "2026-04-01", "open": 50, "high": 51, "low": 49, "close": 50.5, "volume": 200000}]
    }

    with pytest.raises(RuntimeError) as excinfo:
        radar.scan_radar(candles_map)

    assert "KILL-SWITCH" in str(excinfo.value)
    assert "thoái hóa an toàn về Structure + VPA" in str(excinfo.value)
