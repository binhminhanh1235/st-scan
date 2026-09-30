"""
WFE L3 — RISK & STATE MACHINE VỊ THẾ
Architecture Contract:
1. SL1 = min(Low[-5:-1]) - 0.8 * ATR14.
2. Gap fill simulation (open < SL -> fill open; limit floor -> fill floor).
3. Total risk across 2 tranches <= 6.5% NAV at p99.
4. When Tranche 2 triggers, stop loss for both tranches is raised to prior swing low / test low.
5. State machine: ENTRY -> ADD -> HOLD -> DE-RISK -> EXIT with full transition trace.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple
import random
import numpy as np
from wfe.config.registry import RiskConfig, compute_params_hash
from wfe.data.pit_feed import MarketBar


class PositionState(str, Enum):
    IDLE = "IDLE"
    ENTRY = "ENTRY"      # Tranche 0 or 1 active
    ADD = "ADD"          # Tranche 2 added
    HOLD = "HOLD"        # Riding trend towards target
    DE_RISK = "DE_RISK"  # Taking partial profit or tightening stops
    EXIT = "EXIT"        # Position closed


@dataclass
class StateTransitionTrace:
    from_state: str
    to_state: str
    trigger_rule: str
    current_value: float
    threshold_value: float
    timestamp: str
    notes: str


@dataclass
class PositionRiskProfile:
    entry_price: float
    current_price: float
    sl1: float
    current_sl: float
    risk_pct: float
    atr14: float
    p99_simulated_loss_nav: float
    is_risk_acceptable: bool
    tranche_count: int


def compute_atr14(bars: List[MarketBar]) -> float:
    """Computes current ATR 14 from closed bars using Wilder's smoothing."""
    n = len(bars)
    if n < 15:
        return (bars[-1].high - bars[-1].low) if bars else 1.0
    tr_list = []
    for i in range(1, n):
        h, l = bars[i].high, bars[i].low
        c_prev = bars[i - 1].close
        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        tr_list.append(tr)

    curr_atr = sum(tr_list[:14]) / 14.0
    for i in range(14, len(tr_list)):
        curr_atr = (curr_atr * 13.0 + tr_list[i]) / 14.0
    return curr_atr


def calculate_sl1(
    bars: List[MarketBar],
    atr14: Optional[float] = None,
    atr_mult: float = 0.80,
    setup: Optional[str] = None,
    event_low: Optional[float] = None
) -> float:
    """
    Computes SL1:
    - Patch V3.3/V3.4 R1 Trigger-Stop Coherence:
      For TEST_SPRING_PHASE_C waiting to test event_low:
      operative_stop <= event_low - 0.5 * atr14 (strict upper bound).
      For BU_LPS_PHASE_D with event_low (LPS test low):
      operative_stop <= event_low - 0.5 * atr14 (strict upper bound).
    - Default swing stop:
      SL1 = min(Low[-5:-1]) - 0.8 * ATR14.
    """
    atr = atr14 if atr14 is not None else compute_atr14(bars)
    curr_price = bars[-1].close if bars else 1.0

    if setup == "TEST_SPRING_PHASE_C" and event_low is not None and event_low > 0:
        buffer = max(0.5 * atr, 0.005 * event_low)
        upper_bound = event_low - buffer
        sl = round(upper_bound, 2)
        if sl > upper_bound:
            sl = round(sl - 0.01, 2)
        return sl

    if setup == "BU_LPS_PHASE_D" and event_low is not None and event_low > 0:
        buffer = max(0.5 * atr, 0.005 * event_low)
        upper_bound = event_low - buffer
        sl = round(upper_bound, 2)
        if sl > upper_bound:
            sl = round(sl - 0.01, 2)
        return sl

    if len(bars) < 6:
        return round(curr_price * 0.95, 2)

    recent_low_5 = min(b.low for b in bars[-6:-1])
    sl = round(recent_low_5 - atr_mult * atr, 2)

    if (curr_price - sl) < 0.8 * atr:
        sl = round(curr_price - 1.0 * atr, 2)

    return sl


def get_trigger_stop_audit(event_low: float, atr14: float, stop: float) -> Dict[str, Any]:
    """Computes R1 Trigger-Stop Audit parameters."""
    l_rounded = round(event_low, 2)
    atr_rounded = round(atr14, 2)
    upper_bound = round(l_rounded - 0.5 * atr_rounded, 3)
    buffer_amt = round(l_rounded - upper_bound, 3)
    buffer_pct = round((buffer_amt / l_rounded) * 100.0, 2) if l_rounded > 0 else 0.0
    passed = stop <= upper_bound
    return {
        "L": l_rounded,
        "ATR14_current": atr_rounded,
        "buffer_pct": buffer_pct,
        "stop": round(stop, 2),
        "upper_bound": upper_bound,
        "pass": passed
    }



def simulate_gap_floor_risk(
    entry_price: float,
    sl: float,
    nav_allocation_pct: float = 0.20,  # e.g. 20% NAV allocated
    num_simulations: int = 5000,
    floor_pct: float = 0.07,  # 7% HOSE daily limit
    seed: Optional[int] = None,
    gap_event_probs: Optional[Tuple[float, float, float]] = None,
    slippage_range: Tuple[float, float] = (0.01, 0.03)
) -> Dict[str, float]:
    """
    Monte Carlo simulation of gap-down and floor fill slippage.

    Patch V3.5 fixes:
      - Deterministic reproducibility: pass `seed` (recorded in the audit trace) so
        identical inputs always yield identical p99 — required by the repo's own
        audit-trail contract. Without a seed the previous version produced drifting
        numbers run-to-run.
      - Vectorized NumPy execution (was a Python loop over random.random()).
      - Empirical calibration hook: `gap_event_probs` = (p_normal_fill, p_gap_down,
        p_floor_lock) can be estimated from HOSE history (frequency of opens below
        stop, frequency of floor-locked sessions) instead of the hardcoded
        90/8/2 scenario prior; `slippage_range` likewise.

    Returns dict with p99/p95 loss (% NAV) and realized event frequencies, so the
    caller can log the empirical-vs-prior divergence into the trace.
    """
    if entry_price <= 0 or sl >= entry_price:
        return {"p99_loss_nav": 0.0, "p95_loss_nav": 0.0,
                "p_normal": 1.0, "p_gap": 0.0, "p_floor": 0.0}

    rng = np.random.default_rng(seed)
    nominal_loss_pct = (entry_price - sl) / entry_price

    pn, pg, pf = gap_event_probs if gap_event_probs else (0.90, 0.08, 0.02)
    total = pn + pg + pf
    probs = np.array([pn / total, pg / total, pf / total])

    # Categorical draw: 0 = normal fill at SL, 1 = gap-down slippage, 2 = floor lock
    events = rng.choice(3, size=num_simulations, p=probs)
    lo, hi = slippage_range
    slippages = rng.uniform(lo, hi, size=num_simulations)

    actual_loss_pct = np.full(num_simulations, nominal_loss_pct)
    gap_mask = events == 1
    floor_mask = events == 2
    actual_loss_pct[gap_mask] = np.minimum(nominal_loss_pct + slippages[gap_mask], floor_pct * 1.5)
    actual_loss_pct[floor_mask] = np.maximum(nominal_loss_pct, floor_pct)

    losses_pct_nav = np.sort(actual_loss_pct * nav_allocation_pct)
    p99 = float(losses_pct_nav[min(int(0.99 * len(losses_pct_nav)), len(losses_pct_nav) - 1)])
    p95 = float(losses_pct_nav[min(int(0.95 * len(losses_pct_nav)), len(losses_pct_nav) - 1)])

    return {
        "p99_loss_nav": round(p99, 4),
        "p95_loss_nav": round(p95, 4),
        "p_normal": round(float((events == 0).mean()), 4),
        "p_gap": round(float(gap_mask.mean()), 4),
        "p_floor": round(float(floor_mask.mean()), 4),
    }


class PositionStateMachine:
    """
    Position Lifecycle Manager: ENTRY -> ADD -> HOLD -> DE-RISK -> EXIT.
    """

    def __init__(self, symbol: str, config: Optional[RiskConfig] = None):
        self.symbol = symbol
        self.config = config or RiskConfig()
        self.state = PositionState.IDLE
        self.entry_price: float = 0.0
        self.current_sl: float = 0.0
        self.sl1: float = 0.0
        self.tranches_open: int = 0
        self.size_pct: float = 0.0
        self.traces: List[StateTransitionTrace] = []

    def open_entry(self, entry_price: float, sl: float, size_pct: float, date_str: str, note: str = "") -> None:
        """Transition IDLE -> ENTRY."""
        old_state = self.state.value
        self.state = PositionState.ENTRY
        self.entry_price = entry_price
        self.sl1 = sl
        self.current_sl = sl
        self.tranches_open = 1
        self.size_pct = size_pct
        self.traces.append(StateTransitionTrace(
            from_state=old_state,
            to_state=self.state.value,
            trigger_rule="Tranche 1 Triggered",
            current_value=entry_price,
            threshold_value=sl,
            timestamp=date_str,
            notes=note or f"Opened Tranche 1 at {entry_price}, initial SL={sl}"
        ))

    def add_tranche2(self, add_price: float, new_sl: float, additional_size: float, date_str: str, note: str = "") -> None:
        """
        Transition ENTRY -> ADD.
        Raises stop loss for BOTH tranches to new_sl (prior swing low).
        """
        old_state = self.state.value
        self.state = PositionState.ADD
        self.tranches_open = 2
        self.size_pct += additional_size
        old_sl = self.current_sl
        self.current_sl = max(self.current_sl, new_sl)  # Stop loss only moves UP
        self.traces.append(StateTransitionTrace(
            from_state=old_state,
            to_state=self.state.value,
            trigger_rule="Tranche 2 Confirmation",
            current_value=add_price,
            threshold_value=self.current_sl,
            timestamp=date_str,
            notes=note or f"Added Tranche 2 at {add_price}. Raised stop loss for BOTH tranches from {old_sl} to {self.current_sl}"
        ))

    def enter_hold(self, current_price: float, date_str: str, note: str = "") -> None:
        """Transition ADD / ENTRY -> HOLD."""
        old_state = self.state.value
        self.state = PositionState.HOLD
        self.traces.append(StateTransitionTrace(
            from_state=old_state,
            to_state=self.state.value,
            trigger_rule="Trend established",
            current_value=current_price,
            threshold_value=self.current_sl,
            timestamp=date_str,
            notes=note or "Holding position towards targets"
        ))

    def de_risk(self, current_price: float, new_sl: float, reduce_pct: float, date_str: str, note: str = "") -> None:
        """Transition HOLD / ENTRY / ADD -> DE_RISK."""
        old_state = self.state.value
        self.state = PositionState.DE_RISK
        self.current_sl = max(self.current_sl, new_sl)
        self.size_pct = max(0.0, self.size_pct * (1.0 - reduce_pct))
        self.traces.append(StateTransitionTrace(
            from_state=old_state,
            to_state=self.state.value,
            trigger_rule="De-risk Trigger",
            current_value=current_price,
            threshold_value=self.current_sl,
            timestamp=date_str,
            notes=note or f"Reduced size by {reduce_pct*100:.0f}%, tightened SL to {self.current_sl}"
        ))

    def exit_position(self, exit_price: float, date_str: str, rule: str, note: str = "") -> None:
        """Transition to EXIT."""
        old_state = self.state.value
        self.state = PositionState.EXIT
        self.tranches_open = 0
        self.size_pct = 0.0
        self.traces.append(StateTransitionTrace(
            from_state=old_state,
            to_state=self.state.value,
            trigger_rule=rule,
            current_value=exit_price,
            threshold_value=self.current_sl,
            timestamp=date_str,
            notes=note or f"Full exit executed at {exit_price} ({rule})"
        ))
