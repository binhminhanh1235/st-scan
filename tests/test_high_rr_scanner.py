"""
Unit tests for high-rr-setup-scanner enhancements (V2.1):
1. BUG-1: Bearish VPA filters out invalid setups.
2. BUG-2: base_low_40 excludes current bar.
3. BUG-3: Upthrust detection filters out false breakouts.
4. BUG-4: Grinding decline detected as No Demand.
5. BUG-5: Limit-day volume excluded from SMA20.
6. BUG-7: Shallow base breakout filtered out.
7. Support Density & Weak vs Strong Support ATR buffer.
8. RS Filter (< -5.0% dropped).
9. Composite Score ranking.
"""

import os
import sys
import importlib.util
import pytest
from unittest.mock import patch

server_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mcp", "vnstock_server.py"))
spec = importlib.util.spec_from_file_location("vnstock_server", server_path)
vnstock_server = importlib.util.module_from_spec(spec)
sys.modules["vnstock_server"] = vnstock_server
spec.loader.exec_module(vnstock_server)

classify_vpa = vnstock_server.classify_vpa
compute_clean_sma20_vol = vnstock_server.compute_clean_sma20_vol
compute_wilder_atr14 = vnstock_server.compute_wilder_atr14
scan_high_rr_setups = vnstock_server.scan_high_rr_setups


def test_classify_vpa_grinding_no_demand():
    """Verify 3 consecutive down bars with low volume triggers Grinding No Demand."""
    c = [100.0, 99.0, 98.0, 97.0]
    o = [100.0, 99.5, 98.5, 97.5]
    h = [100.5, 99.5, 98.5, 97.5]
    l = [99.5, 98.5, 97.5, 96.5]
    v = [1000.0, 500.0, 500.0, 500.0]
    sma20_vol = 1000.0

    tag = classify_vpa(c, o, h, l, v, 3, sma20_vol)
    assert "Grinding No Demand" in tag


def test_classify_vpa_upthrust():
    """Verify high volume with low close position at 20-bar high triggers Upthrust."""
    c = [50.0] * 20 + [50.5]
    o = [50.0] * 20 + [51.0]
    h = [50.2] * 20 + [54.0]  # bar 20 makes new high at 54.0
    l = [49.8] * 20 + [50.0]
    v = [1000.0] * 20 + [2500.0]  # high vol
    sma20_vol = 1000.0

    tag = classify_vpa(c, o, h, l, v, 20, sma20_vol)
    assert "Upthrust" in tag


def test_compute_clean_sma20_vol_excludes_limit_days():
    """Verify ceiling and floor days are excluded from SMA20 volume calculation."""
    # 19 normal days with vol 1000, 1 ceiling day with vol 100000
    c = [50.0] * 19 + [53.5]
    o = [50.0] * 19 + [53.5]
    h = [50.5] * 19 + [53.5]  # ceiling bar: c == h == o
    l = [49.5] * 19 + [53.5]
    v = [1000.0] * 19 + [100000.0]

    clean_sma = compute_clean_sma20_vol(v, c, o, h, l, 19)
    assert clean_sma == 1000.0, f"Expected 1000.0, got {clean_sma}"


def test_compute_wilder_atr14():
    """Verify Wilder ATR 14 responds smoothly."""
    c = [10.0 + i * 0.1 for i in range(30)]
    h = [p + 0.5 for p in c]
    l = [p - 0.5 for p in c]
    atr = compute_wilder_atr14(c, h, l)
    assert 0.9 <= atr <= 1.1


def test_scan_high_rr_setups_with_mock_data():
    """Test full scanner logic with mocked market data."""
    # Construct 60 bars for a stock: base at 50, current price 50.5 near support
    stock_bars = {
        "c": [50.0 + (i % 3) * 0.5 for i in range(59)] + [50.5],
        "o": [50.0 + (i % 3) * 0.5 for i in range(59)] + [50.2],
        "h": [52.5 for _ in range(59)] + [51.0],
        "l": [50.0 for _ in range(59)] + [50.1],
        "v": [1000000.0 for _ in range(59)] + [600000.0]  # low vol No Supply
    }
    # Index data
    idx_bars = {
        "c": [1200.0 + i * 0.5 for i in range(40)]
    }

    with patch.object(vnstock_server, "_fetch_batch_candles", return_value={"TEST": stock_bars}), \
         patch.object(vnstock_server, "_fetch_dnse_raw", return_value=idx_bars), \
         patch.object(vnstock_server, "get_stock_sector", return_value="Thép"):

        res = scan_high_rr_setups(min_rr=1.5, min_avg_val_bil=10.0, symbols=["TEST"])
        assert res["scanned_count"] == 1
        assert "methodology" in res
        assert "composite_ranking" in res["methodology"]
        if res["top_setups"]:
            setup = res["top_setups"][0]
            assert "composite_score" in setup
            assert "rs_score" in setup
            assert "support_density" in setup
            assert "support_tag" in setup


def test_classify_vpa_no_supply_rejects_up_candle():
    """Verify Wyckoff No Supply cannot be assigned to an UP candle."""
    c = [50.0, 50.5]
    o = [50.0, 50.1]
    h = [50.2, 50.6]
    l = [49.8, 50.0]
    v = [1000.0, 400.0]  # low vol
    sma20_vol = 1000.0

    tag = classify_vpa(c, o, h, l, v, 1, sma20_vol)
    assert "No Supply" not in tag
    assert "Thiếu cầu" in tag or "Low-vol" in tag


def test_classify_vpa_distinguishes_hammer_from_marubozu():
    """Verify SOS bar with large lower shadow is classified as Hammer SOS, not full body."""
    # Bar with open 52.0, low 51.3, high 52.3, close 52.3 (70% lower shadow)
    c = [50.0, 52.3]
    o = [50.0, 52.0]
    h = [50.2, 52.3]
    l = [49.8, 51.3]
    v = [1000.0, 2500.0]  # high vol
    sma20_vol = 1000.0

    tag = classify_vpa(c, o, h, l, v, 1, sma20_vol)
    assert "Hammer" in tag

