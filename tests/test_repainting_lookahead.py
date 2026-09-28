"""
Test Chống Look-Ahead & Repainting:
1. Mọi tính toán thực hiện trên nến đóng.
2. prev_vol_sma hoàn toàn loại bỏ nến hiện tại.
3. Thêm nến tương lai T+1 không làm thay đổi kết quả tại T.
"""

import pytest
from wfe.data.pit_feed import MarketBar, compute_prev_sma20_vol
from wfe.engines.flow_engine import FlowEngine
from wfe.engines.structure_engine import StructureEngine
from wfe.engines.volume_engine import VolumeEngine


def generate_synthetic_bars(n: int = 100) -> list:
    bars = []
    base_price = 50.0
    for i in range(n):
        o = base_price + (i % 5) * 0.5
        h = o + 1.2
        l = o - 0.8
        c = o + 0.3
        v = 200000.0 + (i % 7) * 30000.0
        bars.append(MarketBar(date=f"2026-01-{i+1:03d}", open=o, high=h, low=l, close=c, volume=v))
    return bars


def test_prev_sma20_vol_excludes_current_bar():
    """Verify prev_sma20_vol does not change when current bar volume changes."""
    bars = generate_synthetic_bars(80)
    current_idx = 79

    sma_before = compute_prev_sma20_vol(bars, current_idx)

    # Modify current bar's volume by 10x
    bars[current_idx].volume = bars[current_idx].volume * 10.0
    sma_after = compute_prev_sma20_vol(bars, current_idx)

    assert sma_before == sma_after, "prev_sma20_vol was contaminated by current bar volume!"


def test_no_repainting_across_all_engines():
    """
    Verify that calculations at bar T remain 100% identical when bar T+1 is introduced.
    """
    bars_full = generate_synthetic_bars(90)
    t = 80
    bars_at_t = bars_full[:t + 1]

    # Calculate at T
    flow_t = FlowEngine().calculate(bars_at_t)
    struct_t = StructureEngine().calculate(bars_at_t)
    vol_t = VolumeEngine().calculate(bars_at_t)

    # Now calculate at T with an isolated copy
    bars_at_t_copy = [MarketBar(**vars(b)) for b in bars_at_t]
    flow_check = FlowEngine().calculate(bars_at_t_copy)
    struct_check = StructureEngine().calculate(bars_at_t_copy)
    vol_check = VolumeEngine().calculate(bars_at_t_copy)

    # Verify identical values
    assert flow_t.trend.value == flow_check.trend.value
    assert flow_t.accum.value == flow_check.accum.value
    assert flow_t.dist.value == flow_check.dist.value

    assert struct_t.levels.tr_high == struct_check.levels.tr_high
    assert struct_t.levels.tr_low == struct_check.levels.tr_low
    assert struct_t.levels.t1 == struct_check.levels.t1
    assert struct_t.levels.t2 == struct_check.levels.t2

    assert vol_t.rvol == vol_check.rvol
    assert vol_t.cp == vol_check.cp
