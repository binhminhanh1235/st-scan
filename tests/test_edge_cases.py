"""
Test Edge Cases (Definition of Done #3):
1. Volume = 0
2. Doji (High == Low -> CP = 0.5)
3. Lịch sử < 70 nến -> data_ok = False, score = None (không chấm 0 ngầm)
4. Ex-date spike loại khỏi SMA20
5. Phiên trần/sàn -> limit_day = True, volume không vào SMA20
6. NaN / thiếu dữ liệu -> data_ok = False
"""

import pytest
import math
from wfe.data.pit_feed import PITFeed, MarketBar, compute_prev_sma20_vol
from wfe.engines.flow_engine import FlowEngine
from wfe.engines.structure_engine import StructureEngine
from wfe.engines.volume_engine import VolumeEngine


def test_doji_candle_close_position():
    """Verify Doji candle with High == Low outputs CP = 0.50 without ZeroDivisionError."""
    bars = [
        MarketBar(date=f"2026-01-{i+1:02d}", open=50.0, high=50.0, low=50.0, close=50.0, volume=10000.0)
        for i in range(25)
    ]
    vol_out = VolumeEngine().calculate(bars)
    assert vol_out.data_ok is True
    assert vol_out.cp == 0.50, f"Expected CP=0.50 for doji, got {vol_out.cp}"


def test_zero_volume_handling():
    """Verify system handles zero volume cleanly without exceptions."""
    bars = [
        MarketBar(date=f"2026-01-{i+1:02d}", open=50.0, high=51.0, low=49.0, close=50.0, volume=0.0)
        for i in range(80)
    ]
    flow_out = FlowEngine().calculate(bars)
    assert flow_out.data_ok is True
    assert flow_out.trend.value == 0.0

    vol_out = VolumeEngine().calculate(bars)
    assert vol_out.data_ok is True
    assert vol_out.rvol == 0.0 or vol_out.rvol == 1.0


def test_insufficient_history_returns_none_not_zero():
    """Verify history < 70 bars returns data_ok=False and score=None (not implicitly 0)."""
    feed = PITFeed(min_bars=70)
    raw = [
        {"date": f"2026-01-{i+1:02d}", "open": 50.0, "high": 51.0, "low": 49.0, "close": 50.0, "volume": 100000.0}
        for i in range(40)  # Only 40 bars
    ]
    series = feed.process_raw_candles("TEST", raw)
    assert series.data_ok is False
    assert "Insufficient history" in series.rejection_reason

    # Flow Engine check on <70 bars
    flow_out = FlowEngine().calculate(series.bars)
    assert flow_out.data_ok is False
    assert flow_out.trend.value is None, "Should be None, must not be implicitly 0!"
    assert flow_out.accum.value is None
    assert flow_out.dist.value is None


def test_nan_feed_returns_data_ok_false():
    """Verify NaN in feed sets data_ok=False and score=None."""
    feed = PITFeed(min_bars=70)
    raw = [
        {"date": f"2026-01-{i+1:02d}", "open": 50.0, "high": 51.0, "low": 49.0, "close": 50.0, "volume": 100000.0}
        for i in range(80)
    ]
    # Inject NaN at bar 45
    raw[45]["close"] = float("nan")

    series = feed.process_raw_candles("NAN_TEST", raw)
    assert series.data_ok is False
    assert "Missing/NaN values" in series.rejection_reason


def test_limit_day_and_ex_date_spike_excluded_from_sma20():
    """Verify limit day volume and ex-date spike are excluded from prev_sma20_vol."""
    bars = [
        MarketBar(date=f"2026-01-{i+1:02d}", open=50.0, high=51.0, low=49.0, close=50.0, volume=100000.0)
        for i in range(30)
    ]

    # Baseline SMA
    normal_sma = compute_prev_sma20_vol(bars, 29)
    assert normal_sma == 100000.0

    # Introduce a 10x volume spike on an ex-date bar within the window
    bars[25].is_ex_date = True
    bars[25].volume = 1000000.0  # 10x spike

    # Introduce a limit day bar with 5x volume
    bars[26].is_limit_day = True
    bars[26].volume = 500000.0

    clean_sma = compute_prev_sma20_vol(bars, 29)
    # Since ex_date and limit_day are excluded, the SMA of the remaining bars should remain 100000.0
    assert clean_sma == 100000.0, f"Spike was not excluded! Got {clean_sma}"


def test_limit_up_exceeding_t1_routes_to_watchlist_with_zero_size():
    """
    Unit test bắt buộc (V3.1):
    Bơm vào một mã đã tăng trần vượt T1, đầu ra phải là watchlist + sizing 0, không được phép in T1 dưới giá.
    """
    from wfe.scanner import WFEScanner
    
    # Construct base candles
    candles = []
    for i in range(120):
        candles.append({
            "date": f"2026-01-{i+1:03d}",
            "open": 50.0,
            "high": 52.0,
            "low": 48.0,
            "close": 50.0,
            "volume": 200000.0
        })
    # Last bar: massive limit-up breakout to 75.0 (far above TR_High=52.0 and T1)
    candles.append({
        "date": "2026-05-01",
        "open": 72.0,
        "high": 75.0,
        "low": 71.0,
        "close": 75.0,
        "volume": 500000.0
    })

    scanner = WFEScanner()
    output = scanner.analyze_symbol("LIMIT_UP_TEST", candles)

    # 1. Classification must be WATCHLIST
    assert output.classification == "WATCHLIST"

    # 2. Sizing must be 0% NAV
    assert output.policy.size_pct == 0.0

    # 3. T1 must NOT be below current price (either None or promoted above 75.0)
    t1 = output.structure.levels["t1"]
    if t1 is not None:
        assert t1 > output.current_price
    else:
        assert output.structure.levels["target_tag"] == "[TARGET_EXHAUSTED]"

    # 4. Tranche plans must not be actionable
    assert not any(tp["is_eligible"] for tp in output.policy.tranche_plans)
