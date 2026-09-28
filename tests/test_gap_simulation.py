"""
Test Gap-Down & Limit Floor Risk Simulation (Definition of Done #4):
Mô phỏng fill gap và giá sàn: tổng risk 2 tranche <= 6.5% NAV ở phân vị p99.
"""

import pytest
from wfe.risk.state_machine import simulate_gap_floor_risk


def test_p99_risk_within_6_5_percent_nav():
    """Verify that p99 portfolio risk under gap-down / floor slippage is <= 6.5% NAV."""
    entry_price = 50.0
    sl = 47.5  # 5% stop loss
    nav_allocation = 0.25  # 25% NAV allocated across 2 tranches

    p99_loss_nav = simulate_gap_floor_risk(
        entry_price=entry_price,
        sl=sl,
        nav_allocation_pct=nav_allocation,
        num_simulations=10000,
        floor_pct=0.07  # 7% HOSE floor
    )

    # 6.5% NAV is 0.065
    assert p99_loss_nav <= 0.065, f"p99 loss {p99_loss_nav*100:.2f}% NAV exceeded 6.5% NAV ceiling!"


def test_extreme_slippage_still_capped():
    """Verify extreme gap is controlled by sizing limits."""
    entry_price = 100.0
    sl = 93.0  # 7% nominal SL
    nav_allocation = 0.30  # Max 30% NAV per sector / position

    p99_loss_nav = simulate_gap_floor_risk(
        entry_price=entry_price,
        sl=sl,
        nav_allocation_pct=nav_allocation,
        num_simulations=5000,
        floor_pct=0.07
    )
    # Even with floor slippage, loss cannot exceed allocation * max gap
    assert p99_loss_nav <= 0.065
