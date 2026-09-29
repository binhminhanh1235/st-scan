"""
WFE L1 — VOLUME ENGINE (VPA = Kính hiển vi sự kiện)
Architecture Contract:
1. Độc lập tuyệt đối: không import Flow hay Structure Engine.
2. Vai trò: kính hiển vi kiểm định chất lượng từng nến & sự kiện.
3. Xuất RVol, CP (doji -> 0.5), cờ VPA, event-quality score cho từng event ID.
4. Không in từ ngữ dự báo.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from wfe.config.registry import VolumeEngineConfig, compute_params_hash
from wfe.data.pit_feed import MarketBar, compute_prev_sma20_vol


@dataclass
class EventQuality:
    event_id: str
    event_type: str
    quality_score: float  # 0 to 100
    rvol: float
    cp: float
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VPAFlags:
    dry_up: bool  # RVol <= 0.9 for >= 3 bars
    absorption: bool
    exhaustion: bool
    breakout_vol: bool
    limit_day: bool


@dataclass
class VolumeOutput:
    rvol: float
    cp: float
    flags: VPAFlags
    event_qualities: Dict[str, EventQuality]
    dry_up_bars_count: int
    data_ok: bool
    params_hash: str
    diagnostics: Dict[str, Any] = field(default_factory=dict)


def _compute_atr14(bars: List[MarketBar]) -> float:
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


class VolumeEngine:
    """Volume Engine analyzes candle-level VPA metrics and event qualities."""

    def __init__(self, config: Optional[VolumeEngineConfig] = None):
        self.config = config or VolumeEngineConfig()

    @property
    def params_hash(self) -> str:
        return self.config.params_hash

    def calculate(
        self,
        bars: List[MarketBar],
        events_to_evaluate: Optional[List[Dict[str, Any]]] = None
    ) -> VolumeOutput:
        cfg = self.config
        p_hash = self.params_hash

        if not bars or len(bars) < 20:
            return VolumeOutput(
                rvol=1.0,
                cp=0.5,
                flags=VPAFlags(dry_up=False, absorption=False, exhaustion=False, breakout_vol=False, limit_day=False),
                event_qualities={},
                dry_up_bars_count=0,
                data_ok=False,
                params_hash=p_hash,
                diagnostics={"reason": "insufficient_bars"}
            )

        n = len(bars)
        last_bar = bars[-1]

        # 1. Previous SMA20 Volume (strictly closed bars prior to last_bar)
        prev_sma20 = compute_prev_sma20_vol(bars, n - 1)
        rvol = round(last_bar.volume / prev_sma20, 2) if prev_sma20 > 0 else 1.0

        # 2. Close Position (CP)
        spread = last_bar.high - last_bar.low
        if spread <= 1e-6:
            cp = cfg.default_doji_cp  # Doji -> 0.50
        else:
            cp = round((last_bar.close - last_bar.low) / spread, 3)

        # 3. VPA Flags
        # (a) Dry-up: RVol <= dry_up_rvol_max for >= dry_up_min_bars
        dry_up_count = 0
        for i in range(n - 1, -1, -1):
            p_sma = compute_prev_sma20_vol(bars, i)
            rv = (bars[i].volume / p_sma) if p_sma > 0 else 1.0
            if rv <= cfg.dry_up_rvol_max:
                dry_up_count += 1
            else:
                break
        dry_up = dry_up_count >= cfg.dry_up_min_bars

        # (b) Absorption: down candle, vol_ratio >= 1.2, but narrow body
        is_down = last_bar.close < (bars[-2].close if n >= 2 else last_bar.open)
        body = abs(last_bar.close - last_bar.open)
        atr14 = _compute_atr14(bars)
        absorption = bool(
            is_down
            and rvol >= cfg.absorption_rvol_min
            and cp >= 0.40
            and body <= cfg.absorption_body_max_atr * atr14
        )

        # (c) Exhaustion: high vol, but low CP
        exhaustion = bool(rvol >= cfg.exhaustion_rvol_min and cp <= cfg.exhaustion_cp_max)

        # (d) Breakout Vol
        breakout_vol = bool(rvol >= cfg.breakout_rvol_min and cp >= 0.70)

        flags = VPAFlags(
            dry_up=dry_up,
            absorption=absorption,
            exhaustion=exhaustion,
            breakout_vol=breakout_vol,
            limit_day=last_bar.is_limit_day
        )

        # 4. Evaluate Event Quality for passed events (from Policy/Caller)
        event_qualities: Dict[str, EventQuality] = {}
        if events_to_evaluate:
            for ev in events_to_evaluate:
                ev_id = ev.get("event_id", "UNKNOWN")
                ev_type = ev.get("event_type", "EVENT")
                bar_idx = ev.get("bar_index", n - 1)
                bar_idx = min(n - 1, max(0, bar_idx))

                ev_bar = bars[bar_idx]
                p_sma_ev = compute_prev_sma20_vol(bars, bar_idx)
                ev_rvol = (ev_bar.volume / p_sma_ev) if p_sma_ev > 0 else 1.0
                ev_spread = ev_bar.high - ev_bar.low
                ev_cp = (ev_bar.close - ev_bar.low) / ev_spread if ev_spread > 0 else 0.5

                quality_score = 50.0

                if ev_type in ("SPRING", "TEST"):
                    # Quality: depletion of vol (low rvol) + bullish close position
                    vol_dry_factor = max(0.0, 1.0 - min(1.0, ev_rvol))
                    quality_score = round((vol_dry_factor * 0.5 + ev_cp * 0.5) * 100.0, 1)
                elif ev_type in ("MINOR_SOS", "SOS"):
                    # sos_quality = RVol * CP, normalized to 100
                    raw_q = ev_rvol * ev_cp
                    quality_score = round(min(100.0, (raw_q / 2.0) * 100.0), 1)
                elif ev_type == "BU_LPS":
                    # Pullback quality: low rvol, high cp
                    vol_dry_factor = max(0.0, 1.0 - min(1.0, ev_rvol))
                    quality_score = round((vol_dry_factor * 0.6 + ev_cp * 0.4) * 100.0, 1)
                elif ev_type in ("UT_UTAD", "SOW"):
                    # Distribution quality: high vol, low cp
                    quality_score = round((min(2.0, ev_rvol) / 2.0 * 0.5 + (1.0 - ev_cp) * 0.5) * 100.0, 1)

                event_qualities[ev_id] = EventQuality(
                    event_id=ev_id,
                    event_type=ev_type,
                    quality_score=quality_score,
                    rvol=round(ev_rvol, 2),
                    cp=round(ev_cp, 3),
                    details={"bar_idx": bar_idx, "spread": round(ev_spread, 2)}
                )

        return VolumeOutput(
            rvol=rvol,
            cp=cp,
            flags=flags,
            event_qualities=event_qualities,
            dry_up_bars_count=dry_up_count,
            data_ok=True,
            params_hash=p_hash,
            diagnostics={
                "prev_sma20": int(prev_sma20),
                "last_volume": int(last_bar.volume),
                "dry_up_count": dry_up_count
            }
        )
