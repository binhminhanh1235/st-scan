"""
WFE Parameter Registry - Architecture Contract Rule #4
Every hard threshold is a configurable default awaiting percentile calibration,
versioned, and tracked with SHA256 hashes (params_hash).
"""

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, Any


def compute_params_hash(params: Dict[str, Any]) -> str:
    """Compute deterministic SHA256 hash of a parameters dictionary."""
    serialized = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


@dataclass
class FlowEngineConfig:
    version: str = "3.0.0"
    rsi_period: int = 50
    rsi_scale: float = 2.5
    cap_in_box: float = 1.5
    cap_breakout: float = 2.5
    trend_collapse_threshold: float = 15.0
    trend_collapse_prior_min: float = 50.0
    trend_collapse_high_lookback: int = 20
    # flow_accum weights
    w_accum_dv_contr: float = 0.25
    w_accum_absorption: float = 0.25
    w_accum_obv_div: float = 0.25
    w_accum_udr: float = 0.15
    w_accum_test_depletion: float = 0.10
    # flow_dist weights
    w_dist_effort_no_result: float = 0.30
    w_dist_obv_div_neg: float = 0.30
    w_dist_up_vol_exhaust: float = 0.20
    w_dist_down_vol_expansion: float = 0.10
    w_dist_ut_bonus: float = 0.10
    rolling_percentile_window: int = 250

    @property
    def params_hash(self) -> str:
        return compute_params_hash(asdict(self))


@dataclass
class StructureEngineConfig:
    version: str = "3.0.0"
    tr_primary_start: int = -90
    tr_primary_end: int = -20
    tr_shift1_start: int = -100
    tr_shift1_end: int = -25
    tr_shift2_start: int = -80
    tr_shift2_end: int = -15
    stationarity_tolerance: float = 0.05  # 5% drift threshold
    spring_reclaim_max_bars: int = 5
    test_lookback: int = 25
    test_low_ratio_min: float = 0.995
    test_low_ratio_max: float = 1.06
    minor_sos_rvol_min: float = 1.25
    minor_sos_cp_min: float = 0.66
    sos_rvol_min: float = 1.50
    bu_lps_mid_factor: float = 0.99
    bu_lps_event_low_factor: float = 1.02
    bu_lps_rvol_pullback_max: float = 0.80
    major_supply_lookback: int = 130
    t2_buffer_ratio: float = 0.5
    t2_supply_cap_discount: float = 0.98
    t2_min_margin_over_t1: float = 1.15

    @property
    def params_hash(self) -> str:
        return compute_params_hash(asdict(self))


@dataclass
class VolumeEngineConfig:
    version: str = "3.0.0"
    sma_period: int = 20
    dry_up_rvol_max: float = 0.90
    dry_up_min_bars: int = 3
    absorption_rvol_min: float = 1.20
    absorption_body_max_atr: float = 0.40
    exhaustion_rvol_min: float = 1.50
    exhaustion_cp_max: float = 0.35
    breakout_rvol_min: float = 1.50
    default_doji_cp: float = 0.50

    @property
    def params_hash(self) -> str:
        return compute_params_hash(asdict(self))


@dataclass
class PolicyEngineConfig:
    version: str = "3.0.0"
    counter_trend_lookback_old: int = 120
    counter_trend_lookback_mid: int = 60
    counter_trend_lookback_recent: int = 20
    counter_trend_peak_ratio: float = 1.05
    regime_hysteresis_bars: int = 3
    counter_trend_haircut: float = 0.50
    # Confluence threshold for display
    confluence_p_success_min: float = 0.55
    # Tranche buying ladder
    t0_p_min: float = 0.45
    t0_flow_accum_min_pct: float = 70.0
    t0_flow_dist_max_pct: float = 50.0
    t0_ev_min: float = 0.10
    t1_event_quality_min_pct: float = 60.0
    t1_p_min: float = 0.50
    t1_ev_min: float = 0.15
    t2_flow_trend_min_pct: float = 60.0
    t2_rvol_min: float = 1.50
    t2_ev_min: float = 0.20
    # Patch V3.6 (C.1): trần size cấp policy, khớp hard-cap single-stock của
    # PortfolioRegistry (max_nav_per_stock) — scanner vẫn enforce lại tầng của nó.
    max_nav_per_stock: float = 0.25
    # Exit ladder
    exit_dist_pct_min: float = 70.0
    exit_supply_zone_ratio: float = 0.97
    # Sizing base by flow score
    sizing_tiers: Dict[str, float] = field(default_factory=lambda: {
        "tier1_max": 15.0, "tier1_size": 0.30,
        "tier2_max": 25.0, "tier2_size": 0.50,
        "tier3_max": 50.0, "tier3_size": 0.75,
        "tier4_size": 1.00
    })
    # EV Multiplier
    ev_tercile_low_mult: float = 0.75
    ev_tercile_mid_mult: float = 1.00
    ev_tercile_high_mult: float = 1.25
    # Portfolio constraints (Patch V3.2 P1 & V3.3 Q4)
    max_nav_per_sector: float = 0.30
    max_nav_per_stock: float = 0.25      # 25% NAV per stock hard cap
    nav_budget: float = 1.00             # 100% total portfolio allocation
    max_adtv_exit_ratio: float = 0.20    # max 20% ADTV20 exit cap
    reference_nav_bil: float = 15.0      # Reference portfolio NAV = 15 billion VND
    max_concurrent_positions: int = 5

    @property
    def params_hash(self) -> str:
        return compute_params_hash(asdict(self))


@dataclass
class RiskConfig:
    version: str = "3.0.0"
    atr_period: int = 14
    sl1_atr_mult: float = 0.80
    sl1_lookback: int = 5
    max_total_risk_p99_nav: float = 0.065  # 6.5% NAV
    max_single_trade_risk_pct: float = 6.5

    @property
    def params_hash(self) -> str:
        return compute_params_hash(asdict(self))


@dataclass
class OpsConfig:
    version: str = "3.0.0"
    flow_mode: str = "live"  # "live", "down_rank", "off"
    drift_z_threshold: float = 2.0
    drift_window_bars: int = 20
    flow_off_size_mult: float = 0.70
    min_history_bars: int = 70
    min_adtv_bil: float = 15.0

    @property
    def params_hash(self) -> str:
        return compute_params_hash(asdict(self))


@dataclass
class MCDXRadarConfig:
    version: str = "3.0.0"
    tier_strong_threshold: float = 50.0       # E1 Strong
    tier_control_threshold: float = 25.0      # E1 Control
    persist_threshold: float = 25.0           # E2 threshold
    persist_min_bars: int = 3                 # E2 min bars
    persist_window: int = 5                   # E2 window
    sma5_rvol_min: float = 1.10               # E3 standard threshold
    sma5_rvol_no_supply_min: float = 0.70     # E3 relaxed threshold under tight compression and dried selling
    flow_dist_max_pct: float = 60.0           # E4
    # G1 Flow Turn
    g1_turn_threshold: float = 15.0
    g1_prior_bars_le15: int = 8
    g1_lookback: int = 10
    g1_confirm_bars: int = 2
    g1_sma5_rvol_min: float = 1.00
    # G2 Stealth Accumulation
    g2_flow_trend_max: float = 25.0
    g2_flow_accum_min_pct: float = 70.0
    g2_dv_contr_ratio_max: float = 0.75
    g2_obv_div_min: float = 0.15
    g2_compression_range_max: float = 0.12    # 20-bar range <= 12% (phù hợp biên độ VN)
    g_exclude_flow_dist_max_pct: float = 50.0 # distribution bounce exclusion
    # BII Weights
    w_bii_est_trend: float = 0.50
    w_bii_est_persist: float = 0.20
    w_bii_est_rvol5: float = 0.20
    w_bii_est_accum: float = 0.10
    w_bii_est_dist: float = 0.20
    w_bii_emg_accum: float = 0.40
    w_bii_emg_slope: float = 0.25
    w_bii_emg_dv: float = 0.20
    w_bii_emg_obv: float = 0.15
    w_bii_emg_dist: float = 0.15
    bii_freshness_bonus: float = 5.0

    @property
    def params_hash(self) -> str:
        return compute_params_hash(asdict(self))


@dataclass
class WFERegistry:
    """Master registry aggregating all engine and module configurations."""
    version: str = "3.0.0"
    flow: FlowEngineConfig = field(default_factory=FlowEngineConfig)
    structure: StructureEngineConfig = field(default_factory=StructureEngineConfig)
    volume: VolumeEngineConfig = field(default_factory=VolumeEngineConfig)
    policy: PolicyEngineConfig = field(default_factory=PolicyEngineConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    ops: OpsConfig = field(default_factory=OpsConfig)
    mcdx_radar: MCDXRadarConfig = field(default_factory=MCDXRadarConfig)

    def export_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def global_hash(self) -> str:
        return compute_params_hash(self.export_dict())


# Default singleton instance
DEFAULT_REGISTRY = WFERegistry()
