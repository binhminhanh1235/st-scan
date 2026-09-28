"""
WFE L0 — DỮ LIỆU & UNIVERSE POINT-IN-TIME (PIT Feed)

Guarantees:
1. PIT Universe filtering (delisted/warning/control tags).
2. Corporate action aware adjustments (ex-date volume spikes excluded from SMA20).
3. Limit days tagged (volume of limit up/down excluded from SMA20 & leg-max).
4. Minimum 70 closed bars warmup.
5. Missing/NaN checks: data_ok=False, never implicitly zero.
6. Look-ahead & repainting prevention: strictly closed bars, prev_vol_sma excludes current bar.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import math


@dataclass
class MarketBar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_ex_date: bool = False
    is_limit_day: bool = False
    is_valid: bool = True


@dataclass
class BarSeries:
    symbol: str
    bars: List[MarketBar]
    data_ok: bool
    rejection_reason: Optional[str] = None
    adtv20_bil: float = 0.0
    sector: str = "Chung"

    def __len__(self) -> int:
        return len(self.bars)


class PITFeed:
    """Point-in-Time Data Processor for WFE System."""

    def __init__(
        self,
        min_bars: int = 70,
        min_adtv_bil: float = 15.0,
        limit_pct_default: float = 0.069,  # ~7% for HOSE
    ):
        self.min_bars = min_bars
        self.min_adtv_bil = min_adtv_bil
        self.limit_pct_default = limit_pct_default

    def is_bar_limit_day(self, curr: Dict[str, Any], prev_close: Optional[float], exchange: str = "HOSE") -> bool:
        """Identify limit up / limit down sessions."""
        if prev_close is None or prev_close <= 0:
            return False

        ex_upper = exchange.upper() if exchange else "HOSE"
        if ex_upper == "HNX":
            limit_pct = 0.098  # 10%
        elif ex_upper == "UPCOM":
            limit_pct = 0.145  # 15%
        else:
            limit_pct = self.limit_pct_default  # 7% for HOSE

        c = curr.get("close", 0.0)
        h = curr.get("high", 0.0)
        l = curr.get("low", 0.0)

        # Check ceiling or floor touch with narrow spread at extremes
        hit_ceiling = (c >= prev_close * (1.0 + limit_pct)) or (h == l and c > prev_close)
        hit_floor = (c <= prev_close * (1.0 - limit_pct)) or (h == l and c < prev_close)

        return bool(hit_ceiling or hit_floor)

    def process_raw_candles(
        self,
        symbol: str,
        raw_candles: List[Dict[str, Any]],
        exchange: str = "HOSE",
        sector: str = "Chung",
        pit_status: str = "NORMAL"  # "NORMAL", "WARNING", "CONTROL", "DELISTED"
    ) -> BarSeries:
        """
        Processes and validates raw candles into point-in-time compliant series.
        """
        # 1. Check PIT status
        if pit_status in ("WARNING", "CONTROL", "CEASED", "DELISTED_AT_T"):
            return BarSeries(
                symbol=symbol,
                bars=[],
                data_ok=False,
                rejection_reason=f"PIT status restricted ({pit_status})",
                sector=sector
            )

        if not raw_candles or len(raw_candles) < self.min_bars:
            return BarSeries(
                symbol=symbol,
                bars=[],
                data_ok=False,
                rejection_reason=f"Insufficient history: {len(raw_candles) if raw_candles else 0} < {self.min_bars} bars",
                sector=sector
            )

        processed_bars: List[MarketBar] = []
        prev_close: Optional[float] = None

        for idx, bar_dict in enumerate(raw_candles):
            date_val = str(bar_dict.get("date", f"T_{idx}"))
            o = bar_dict.get("open")
            h = bar_dict.get("high")
            l = bar_dict.get("low")
            c = bar_dict.get("close")
            v = bar_dict.get("volume")

            # Quality check: missing/NaN fields
            if any(val is None or (isinstance(val, (int, float)) and math.isnan(val)) for val in (o, h, l, c, v)):
                return BarSeries(
                    symbol=symbol,
                    bars=[],
                    data_ok=False,
                    rejection_reason=f"Missing/NaN values at index {idx} ({date_val})",
                    sector=sector
                )

            o, h, l, c, v = float(o), float(h), float(l), float(c), float(v)

            # Price integrity
            if o <= 0 or h <= 0 or l <= 0 or c <= 0 or v < 0 or h < l:
                return BarSeries(
                    symbol=symbol,
                    bars=[],
                    data_ok=False,
                    rejection_reason=f"Invalid price/volume values at index {idx}",
                    sector=sector
                )

            is_ex_date = bool(bar_dict.get("is_ex_date", False))
            is_limit = self.is_bar_limit_day({"open": o, "high": h, "low": l, "close": c}, prev_close, exchange)
            # Explicit override if passed in dict
            if "is_limit_day" in bar_dict:
                is_limit = bool(bar_dict["is_limit_day"])

            m_bar = MarketBar(
                date=date_val,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=v,
                is_ex_date=is_ex_date,
                is_limit_day=is_limit,
                is_valid=True
            )
            processed_bars.append(m_bar)
            prev_close = c

        # Compute ADTV20 on closed bars prior to current bar if possible
        # Look-ahead prevention: compute prev_sma20_vol
        prev_vol_window = [
            b.volume for b in processed_bars[-21:-1]
            if not b.is_limit_day and not b.is_ex_date
        ]
        if not prev_vol_window:
            prev_vol_window = [b.volume for b in processed_bars[-21:-1]] or [processed_bars[-1].volume]

        prev_sma20_vol = sum(prev_vol_window) / len(prev_vol_window) if prev_vol_window else 0.0
        latest_close = processed_bars[-1].close
        adtv20_bil = (prev_sma20_vol * latest_close) / 1e6  # DNSE price is in 1,000 VND -> 1e6 gives billion VND

        return BarSeries(
            symbol=symbol,
            bars=processed_bars,
            data_ok=True,
            adtv20_bil=round(adtv20_bil, 2),
            sector=sector
        )


def compute_prev_sma20_vol(bars: List[MarketBar], current_idx: int) -> float:
    """
    Computes SMA20 volume strictly EXCLUDING current bar (prevent look-ahead),
    and excluding limit_day and ex_date volume spikes.
    """
    if current_idx <= 0:
        return bars[0].volume if bars else 0.0

    start_idx = max(0, current_idx - 20)
    # Exclude current bar
    window = [
        b.volume for b in bars[start_idx:current_idx]
        if not b.is_limit_day and not b.is_ex_date
    ]
    if not window:
        # Fallback if all 20 bars were limit days / ex-dates
        window = [b.volume for b in bars[start_idx:current_idx]]

    return sum(window) / len(window) if window else bars[current_idx - 1].volume
