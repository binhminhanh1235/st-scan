"""
WFE L4 — OPS, MLOPS & GOVERNANCE
Architecture Contract:
1. Kill-switch per engine: flow_mode in {live, down_rank, off}.
   Flow off -> Policy degrades to Structure+VPA with size * 0.7 without redeploy.
2. Drift Monitor: rolling window 20 bars, alerts on |z| > 2.
3. Incident Playbook: missing volume -> flow off; NaN -> latest closed bar + flag; corporate action error -> freeze.
4. Parity Verification: vectorized vs incremental <= 1e-9.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import numpy as np
from wfe.config.registry import OpsConfig, WFERegistry, DEFAULT_REGISTRY


@dataclass
class DriftAlert:
    metric_name: str
    current_value: float
    rolling_mean: float
    rolling_std: float
    z_score: float
    alert_triggered: bool
    message: str


class KillSwitchManager:
    """Manages operational kill switches for each engine."""

    def __init__(self, initial_flow_mode: str = "live"):
        self.flow_mode = initial_flow_mode  # "live", "down_rank", "off"

    def set_flow_mode(self, mode: str) -> None:
        if mode not in ("live", "down_rank", "off"):
            raise ValueError(f"Invalid flow mode: {mode}")
        self.flow_mode = mode

    @property
    def is_flow_off(self) -> bool:
        return self.flow_mode == "off"

    @property
    def is_flow_down_ranked(self) -> bool:
        return self.flow_mode == "down_rank"


class DriftMonitor:
    """Monitors distribution drift of sub-scores and operational metrics across 20 bars."""

    def __init__(self, window_size: int = 20, z_threshold: float = 2.0):
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.history: Dict[str, List[float]] = {
            "flow_trend": [],
            "flow_accum": [],
            "flow_dist": [],
            "confluence_rate": [],
            "tranche_fill_rate": []
        }

    def record_observation(self, metric_name: str, value: float) -> Optional[DriftAlert]:
        """Record a single metric value and return DriftAlert if |z| > z_threshold."""
        if metric_name not in self.history:
            self.history[metric_name] = []

        hist = self.history[metric_name]
        hist.append(value)
        if len(hist) > self.window_size:
            hist.pop(0)

        if len(hist) < 5:
            # Need minimum history to establish baseline mean/std
            return None

        # Prior window values excluding current
        prior = hist[:-1] if len(hist) > 1 else hist
        mean = float(np.mean(prior))
        std = float(np.std(prior))

        if std < 1e-6:
            z = 0.0
        else:
            z = (value - mean) / std

        alert_triggered = abs(z) > self.z_threshold
        msg = (
            f"DRIFT ALERT: {metric_name} z-score={z:.2f} (|z| > {self.z_threshold}) "
            f"[val={value:.2f}, mean={mean:.2f}, std={std:.2f}]"
            if alert_triggered
            else f"Normal: {metric_name} z-score={z:.2f}"
        )

        return DriftAlert(
            metric_name=metric_name,
            current_value=value,
            rolling_mean=mean,
            rolling_std=std,
            z_score=round(z, 2),
            alert_triggered=alert_triggered,
            message=msg
        )


class IncidentPlaybook:
    """Automated incident response actions."""

    @staticmethod
    def handle_volume_feed_lost(kill_switch: KillSwitchManager) -> Dict[str, Any]:
        """Triggered when volume feed is unavailable or corrupt."""
        kill_switch.set_flow_mode("off")
        return {
            "action": "FLOW_ENGINE_OFF",
            "reason": "Volume feed missing or corrupt",
            "policy_degraded": True,
            "size_multiplier": 0.70
        }

    @staticmethod
    def handle_corrupted_corporate_action(date: str) -> Dict[str, Any]:
        """Triggered when corporate action adjustment feed contains errors."""
        return {
            "action": "FREEZE_UNIVERSE",
            "date": date,
            "reason": "Corrupt corporate action feed detected, universe frozen to prevent bad orders."
        }


def verify_parity(vectorized_values: List[float], incremental_values: List[float], tolerance: float = 1e-9) -> bool:
    """
    Verifies that vectorized calculation and incremental bar-by-bar calculation match within tolerance.
    """
    if len(vectorized_values) != len(incremental_values):
        return False
    diffs = [abs(v - inc) for v, inc in zip(vectorized_values, incremental_values)]
    max_diff = max(diffs) if diffs else 0.0
    return max_diff <= tolerance
