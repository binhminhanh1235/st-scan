"""
Regression & feature tests for Unified Invest Scanner V3.6 upgrades:
1. B1 Fix: Per-symbol stateless rolling hysteresis in PolicyEngine / WFEScanner (no cross-symbol leak).
2. B2 Fix: Batch tools `get_relative_strength_batch` & `get_market_depth_and_foreign_batch`.
3. B4 Fix: Scoped `drop_out_manifest` (no state leak when scanning custom symbol subset).
4. B5 & Token Optimization: Flattened top-level fields on `WFESchemaOutput` and stripped `disclaimer` from `to_dict()`.
5. 3-Tier Market Regime Gate (`BULL`, `CAUTION`, `BEAR`) with portfolio budget caps & Breakout veto.
6. Unified Master Scanner (`scan_unified_opportunities`) with Convergence Score, Optimal Buy Zone, When NOT to Buy, When MUST Sell, and Capital Allocation (% NAV).
7. Portfolio Exit Engine (`evaluate_positions_and_exits`) with 3-stage Trailing Stop, 5-rule Spring Wash-out Guard, Active Climax Exit, and T+8 Time-Stop.
"""

import os
import sys
import importlib.util
from unittest.mock import patch

import pytest

from wfe.scanner import WFEScanner

server_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mcp", "vnstock_server.py"))
spec = importlib.util.spec_from_file_location("vnstock_server", server_path)
vnstock_server = importlib.util.module_from_spec(spec)
sys.modules["vnstock_server"] = vnstock_server
spec.loader.exec_module(vnstock_server)


def _make_raw_candles(n=140, base=30.0, old_peak_mult=1.0, recent_peak_mult=1.0):
    import datetime as _dt
    start_dt = _dt.date(2026, 1, 1)
    candles = []
    px = base
    for i in range(n):
        target_mult = 1.0
        if n - 115 <= i < n - 75:
            target_mult = old_peak_mult
        elif n - 55 <= i < n - 25:
            target_mult = recent_peak_mult
        target_px = base * target_mult + (i % 5) * 0.15
        # Smooth daily step within HOSE +/-7% limit so PITFeed never rejects as unadjusted split
        max_step = px * 0.03
        diff = max(-max_step, min(max_step, target_px - px))
        px = round(px + diff, 2)
        dt_str = (start_dt + _dt.timedelta(days=i)).strftime("%Y-%m-%d")
        candles.append({
            "date": dt_str,
            "open": round(px - 0.1, 2),
            "high": round(px + 0.3, 2),
            "low": round(px - 0.2, 2),
            "close": px,
            "volume": 1_200_000.0
        })
    return candles


def test_b1_no_counter_trend_leak_across_symbols():
    """Verify Symbol A (Counter-Trend) does NOT latch Symbol B (Normal) into Counter-Trend."""
    scanner = WFEScanner()
    sym_counter = _make_raw_candles(140, base=40.0, old_peak_mult=1.35, recent_peak_mult=1.0)
    sym_normal = _make_raw_candles(140, base=40.0, old_peak_mult=1.0, recent_peak_mult=1.15)

    res_a = scanner.analyze_symbol("SYM_COUNTER", sym_counter)
    res_b = scanner.analyze_symbol("SYM_NORMAL", sym_normal)

    assert res_a.policy.is_counter_trend is True
    assert res_a.policy.regime_flag == "[Counter-Trend]"
    assert res_b.policy.is_counter_trend is False, "Counter-Trend hysteresis leaked to subsequent normal symbol!"
    assert res_b.policy.regime_flag == "[Normal]"


def test_b4_dropout_manifest_scoped_by_symbols(tmp_path, monkeypatch):
    """Verify scanning a 1-symbol list does not emit drop-outs from a previous broad scan."""
    scanner = WFEScanner()
    c1 = _make_raw_candles(140, base=35.0)
    # Run a 2-symbol scan first
    scanner.scan_universe({"AAA": c1, "BBB": c1}, top_n=5, min_p_success=0.0, min_avg_val_bil=1.0)
    # Now scan a completely different single symbol "CCC"
    res_single = scanner.scan_universe({"CCC": c1}, top_n=5, min_p_success=0.0, min_avg_val_bil=1.0)
    dropped_syms = [d["symbol"] for d in res_single["drop_out_manifest"]]
    assert "AAA" not in dropped_syms and "BBB" not in dropped_syms


def test_b5_flattened_wfe_schema_and_no_disclaimer():
    """Verify top-level flattened fields exist and `disclaimer` is stripped from `to_dict()`."""
    scanner = WFEScanner()
    out = scanner.analyze_symbol("MWG", _make_raw_candles(140, base=50.0))
    d = out.to_dict()

    assert "disclaimer" not in d
    assert "action" in d and d["action"] == d["classification"]
    assert "setup_type" in d
    assert "ev" in d and d["ev"] == out.policy.ev_r
    assert "p_success" in d and d["p_success"] == out.policy.p_success
    assert "no_buy_warnings" in d and isinstance(d["no_buy_warnings"], list)
    assert "must_sell_triggers" in d and isinstance(d["must_sell_triggers"], list)


def test_market_regime_3_tiers():
    """Verify BULL, CAUTION, and BEAR classification on VN-Index."""
    # 1. BULL: VNINDEX well above rising SMA50
    bull_idx = {"c": [1200.0 + i * 2.0 for i in range(60)], "v": [1e8] * 60}
    r_bull = vnstock_server.evaluate_vnindex_regime(bull_idx)
    assert r_bull["tier"] == "BULL"
    assert r_bull["max_portfolio_nav_pct"] == 100.0
    assert r_bull["allow_breakout"] is True

    # 2. CAUTION: VNINDEX slightly below SMA50 (-1.5%)
    caution_prices = [1250.0] * 50 + [1230.0] * 10
    caution_idx = {"c": caution_prices, "v": [1e8] * 60}
    r_caution = vnstock_server.evaluate_vnindex_regime(caution_idx)
    assert r_caution["tier"] == "CAUTION"
    assert r_caution["max_portfolio_nav_pct"] == 40.0
    assert r_caution["allow_breakout"] is False

    # 3. BEAR: VNINDEX >5% below falling SMA50 with distribution days
    bear_prices = [1300.0] * 35 + [1300.0 - i * 6.0 for i in range(25)]
    bear_vols = [1e8] * 35 + [1.5e8 + i * 1e6 for i in range(25)]
    bear_idx = {"c": bear_prices, "v": bear_vols}
    r_bear = vnstock_server.evaluate_vnindex_regime(bear_idx)
    assert r_bear["tier"] == "BEAR"
    assert r_bear["max_portfolio_nav_pct"] <= 10.0
    assert r_bear["allow_breakout"] is False


def test_scan_unified_opportunities_and_governance_fields():
    """Verify `scan_unified_opportunities` returns convergence score and buy/sell/allocation plans."""
    n = 90
    stock_bars = {
        "t": [1700000000 + i * 86400 for i in range(n)],
        "c": [50.0 + (i % 3) * 0.4 for i in range(n - 1)] + [50.3],
        "o": [50.0 + (i % 3) * 0.4 for i in range(n - 1)] + [50.1],
        "h": [53.0 for _ in range(n - 1)] + [50.8],
        "l": [50.0 for _ in range(n - 1)] + [50.0],
        "v": [1_000_000.0 for _ in range(n - 5)] + [850_000.0, 750_000.0, 650_000.0, 580_000.0, 520_000.0]
    }
    idx_bars = {"c": [1200.0 + i * 1.0 for i in range(70)], "v": [1e8] * 70}

    with patch.object(vnstock_server, "_fetch_batch_candles", return_value={"CTG": stock_bars}), \
         patch.object(vnstock_server, "_fetch_dnse_raw", return_value=idx_bars):
        res = vnstock_server.scan_unified_opportunities(
            preset="all",
            min_rr=1.5,
            min_avg_val_bil=10.0,
            symbols=["CTG"],
            include_foreign_flow=False
        )
        assert res["market_regime"]["tier"] == "BULL"
        assert "portfolio_allocation_summary" in res
        assert len(res["top_opportunities"]) == 1
        cand = res["top_opportunities"][0]
        assert cand["symbol"] == "CTG"
        assert "convergence_score" in cand
        assert "optimal_buy_zone" in cand and len(cand["optimal_buy_zone"]) == 2
        assert "capital_allocation" in cand
        assert cand["capital_allocation"]["recommended_nav_pct"] > 0
        assert len(cand["when_not_to_buy"]) >= 3
        assert len(cand["when_must_sell"]) >= 4


def test_evaluate_positions_and_exits_trailing_and_spring():
    """Verify `evaluate_positions_and_exits` handles T1 Trailing Stop ratchet and SL breach."""
    n = 30
    # Stock 1: Winner that hit Target 1 (55.0) and is now at 54.5 -> should ratchet Operative SL >= Entry (50.0)
    win_bars = {
        "t": [1700000000 + i * 86400 for i in range(n)],
        "c": [50.0] * 25 + [52.0, 54.0, 55.2, 54.8, 54.5],
        "o": [50.0] * 25 + [51.0, 52.5, 54.2, 55.0, 54.2],
        "h": [50.5] * 25 + [52.5, 54.5, 55.5, 55.2, 54.9],
        "l": [49.5] * 25 + [51.0, 52.0, 53.8, 54.0, 54.1],
        "v": [1_000_000.0] * n
    }
    # Stock 2: Loser that closed below SL (48.0) at 47.2 -> must trigger 100% sell
    loss_bars = {
        "t": [1700000000 + i * 86400 for i in range(n)],
        "c": [50.0] * 28 + [48.5, 47.2],
        "o": [50.0] * 28 + [49.5, 48.4],
        "h": [50.5] * 28 + [49.5, 48.5],
        "l": [49.5] * 28 + [48.2, 47.0],
        "v": [1_000_000.0] * 28 + [1_500_000.0, 1_800_000.0]
    }
    idx_bars = {"c": [1250.0] * 60, "v": [1e8] * 60}

    with patch.object(vnstock_server, "_fetch_batch_candles", return_value={"VPL": win_bars, "BAD": loss_bars}), \
         patch.object(vnstock_server, "_fetch_dnse_raw", return_value=idx_bars):
        out = vnstock_server.evaluate_positions_and_exits(
            action="evaluate",
            positions=[
                {"symbol": "VPL", "entry_price": 50.0, "stop_loss": 48.0, "target_1": 55.0, "target_2": 58.0, "size_nav_pct": 20.0},
                {"symbol": "BAD", "entry_price": 50.0, "stop_loss": 48.0, "target_1": 54.0, "target_2": 57.0, "size_nav_pct": 15.0}
            ]
        )
        by_sym = {p["symbol"]: p for p in out["positions_evaluated"]}
        assert by_sym["VPL"]["operative_sl"] >= 50.0
        assert "TARGET 1" in by_sym["VPL"]["status_tag"]
        assert "VI PHẠM SL" in by_sym["BAD"]["status_tag"]
        assert by_sym["BAD"]["recommended_remaining_nav_pct"] == 0.0
