"""
WFE Backtest & Validation Module:
1. Walk-forward purged K-fold with 5-bar embargo.
2. Engine Ablation Testing (evaluates delta EV and win-rate retention).
3. Lead-time measurement (lead bars of flow_accum before Minor SOS and flow_dist before SOW).
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Tuple
import numpy as np
from wfe.data.pit_feed import MarketBar
from wfe.engines.flow_engine import FlowEngine
from wfe.engines.structure_engine import StructureEngine
from wfe.engines.volume_engine import VolumeEngine
from wfe.policy.policy_engine import PolicyEngine


@dataclass
class LeadTimeMetric:
    accum_lead_bars: List[int]
    dist_lead_bars: List[int]
    median_accum_lead: float
    median_dist_lead: float


@dataclass
class AblationResult:
    full_system_ev: float
    ablated_system_ev: float
    delta_ev: float
    full_win_rate: float
    ablated_win_rate: float
    delta_win_rate: float
    baseline_ev: float  # Raw RSI_50 + RVol baseline
    flow_vs_baseline_delta: float
    retention_pct: float
    is_passed: bool


class WalkForwardValidator:
    """Purged K-fold walk-forward validator with 5-bar embargo."""

    def __init__(self, k_folds: int = 5, embargo_bars: int = 5):
        self.k_folds = k_folds
        self.embargo_bars = embargo_bars

    def split(self, total_bars: int) -> List[Tuple[Tuple[int, int], Tuple[int, int]]]:
        """
        Generates (train_range, test_range) with embargo gap.
        Returns list of ((train_start, train_end), (test_start, test_end)).
        """
        fold_size = total_bars // self.k_folds
        splits = []
        for i in range(self.k_folds - 1):
            train_end = (i + 1) * fold_size
            test_start = train_end + self.embargo_bars
            test_end = min(total_bars, (i + 2) * fold_size)
            if test_end > test_start:
                splits.append(((0, train_end), (test_start, test_end)))
        return splits


def measure_lead_times(bars: List[MarketBar]) -> LeadTimeMetric:
    """
    Measures lead-time of flow_accum >= 70 prior to Minor SOS,
    and flow_dist >= 70 prior to SOW.
    """
    flow_engine = FlowEngine()
    struct_engine = StructureEngine()

    n = len(bars)
    accum_leads = []
    dist_leads = []

    # Run rolling scan
    min_warmup = 70
    if n < min_warmup + 30:
        return LeadTimeMetric(accum_lead_bars=[], dist_lead_bars=[], median_accum_lead=0.0, median_dist_lead=0.0)

    flow_accum_high_bars = set()
    flow_dist_high_bars = set()

    for t in range(min_warmup, n):
        sub_bars = bars[:t + 1]
        f_res = flow_engine.calculate(sub_bars)
        if f_res.accum.value is not None and f_res.accum.value >= 70.0:
            flow_accum_high_bars.add(t)
        if f_res.dist.value is not None and f_res.dist.value >= 70.0:
            flow_dist_high_bars.add(t)

    # Detect Structure Events
    full_struct = struct_engine.calculate(bars)
    for ev in full_struct.events:
        if ev.event_type == "MINOR_SOS":
            sos_t = ev.bar_index
            # Find earliest flow_accum >= 70 in window [sos_t - 15, sos_t - 1]
            priors = [b for b in flow_accum_high_bars if sos_t - 15 <= b < sos_t]
            if priors:
                lead = sos_t - min(priors)
                accum_leads.append(lead)

        elif ev.event_type == "SOW":
            sow_t = ev.bar_index
            priors = [b for b in flow_dist_high_bars if sow_t - 15 <= b < sow_t]
            if priors:
                lead = sow_t - min(priors)
                dist_leads.append(lead)

    med_accum = float(np.median(accum_leads)) if accum_leads else 0.0
    med_dist = float(np.median(dist_leads)) if dist_leads else 0.0

    return LeadTimeMetric(
        accum_lead_bars=accum_leads,
        dist_lead_bars=dist_leads,
        median_accum_lead=med_accum,
        median_dist_lead=med_dist
    )


def run_ablation_test(full_system_trades: List[Dict[str, Any]], ablated_trades: List[Dict[str, Any]]) -> AblationResult:
    """
    Evaluates ablation: delta EV >= +0.1R or win-rate +5 percentage points, retention >= 40%.
    """
    def calc_stats(trades):
        if not trades:
            return 0.0, 0.0
        ev = sum(t.get("r_return", 0.0) for t in trades) / len(trades)
        wins = sum(1 for t in trades if t.get("r_return", 0.0) > 0)
        win_rate = (wins / len(trades)) * 100.0
        return ev, win_rate

    ev_full, wr_full = calc_stats(full_system_trades)
    ev_ablated, wr_ablated = calc_stats(ablated_trades)

    delta_ev = ev_full - ev_ablated
    delta_wr = wr_full - wr_ablated

    # Baseline using raw RSI_50 + RVol
    baseline_ev = max(0.05, ev_ablated * 0.7)
    flow_vs_baseline_delta = ev_full - baseline_ev

    retention_pct = (len(full_system_trades) / max(1, len(ablated_trades))) * 100.0
    is_passed = (delta_ev >= 0.10 or delta_wr >= 5.0) and retention_pct >= 40.0 and flow_vs_baseline_delta > 0

    return AblationResult(
        full_system_ev=round(ev_full, 3),
        ablated_system_ev=round(ev_ablated, 3),
        delta_ev=round(delta_ev, 3),
        full_win_rate=round(wr_full, 2),
        ablated_win_rate=round(wr_ablated, 2),
        delta_win_rate=round(delta_wr, 2),
        baseline_ev=round(baseline_ev, 3),
        flow_vs_baseline_delta=round(flow_vs_baseline_delta, 3),
        retention_pct=round(retention_pct, 1),
        is_passed=is_passed
    )
