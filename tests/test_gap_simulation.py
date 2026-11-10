"""
Test Gap-Down & Limit Floor Risk Simulation (Definition of Done #4):
Mô phỏng fill gap và giá sàn: tổng risk 2 tranche <= 6.5% NAV ở phân vị p99.
Patch V3.5: API returns a dict (p99/p95 + realized frequencies) and accepts `seed`.
"""

import pytest
from wfe.risk.state_machine import simulate_gap_floor_risk


def test_p99_risk_within_6_5_percent_nav():
    """Verify that p99 portfolio risk under gap-down / floor slippage is <= 6.5% NAV."""
    entry_price = 50.0
    sl = 47.5  # 5% stop loss
    nav_allocation = 0.25  # 25% NAV allocated across 2 tranches

    sim = simulate_gap_floor_risk(
        entry_price=entry_price,
        sl=sl,
        nav_allocation_pct=nav_allocation,
        num_simulations=10000,
        floor_pct=0.07,  # 7% HOSE floor
        seed=42
    )
    p99_loss_nav = sim["p99_loss_nav"]

    # 6.5% NAV is 0.065
    assert p99_loss_nav <= 0.065, f"p99 loss {p99_loss_nav*100:.2f}% NAV exceeded 6.5% NAV ceiling!"


def test_extreme_slippage_still_capped():
    """Verify extreme gap is controlled by sizing limits."""
    entry_price = 100.0
    sl = 93.0  # 7% nominal SL
    nav_allocation = 0.30  # Max 30% NAV per sector / position

    sim = simulate_gap_floor_risk(
        entry_price=entry_price,
        sl=sl,
        nav_allocation_pct=nav_allocation,
        num_simulations=5000,
        floor_pct=0.07,
        seed=7
    )
    p99_loss_nav = sim["p99_loss_nav"]
    # Even with floor slippage, loss cannot exceed allocation * max gap
    assert p99_loss_nav <= 0.065


def test_seeded_simulation_is_deterministic():
    """Patch V3.5: identical inputs + identical seed must reproduce p99 exactly."""
    kwargs = dict(entry_price=50.0, sl=47.0, nav_allocation_pct=0.20,
                  num_simulations=5000, seed=12345)
    a = simulate_gap_floor_risk(**kwargs)
    b = simulate_gap_floor_risk(**kwargs)
    assert a == b, "Seeded Monte Carlo must be byte-for-byte reproducible (audit trail)"


def test_realized_frequencies_match_prior():
    """Realized event frequencies should hover near the configured prior."""
    sim = simulate_gap_floor_risk(
        entry_price=80.0, sl=76.0, nav_allocation_pct=0.15,
        num_simulations=20000, seed=99,
        gap_event_probs=(0.90, 0.08, 0.02)
    )
    assert abs(sim["p_normal"] - 0.90) < 0.02
    assert abs(sim["p_gap"] - 0.08) < 0.02
    assert abs(sim["p_floor"] - 0.02) < 0.02


def test_invalid_inputs_return_zero_dict():
    sim = simulate_gap_floor_risk(entry_price=50.0, sl=55.0)
    assert sim["p99_loss_nav"] == 0.0
    # Patch V3.6: dict mở thêm floor_pct_used/floor_source (audit trace)
    assert set(sim.keys()) == {"p99_loss_nav", "p95_loss_nav", "p_normal", "p_gap",
                               "p_floor", "floor_pct_used", "floor_source"}
