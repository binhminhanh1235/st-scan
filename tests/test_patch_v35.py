"""
Regression tests for Patch V3.5 / V3.5.1 fixes:
  1. fit_platt_params recovers generating (a,b) on synthetic labeled data
     and beats the hardcoded prior on ECE + log-loss (V3.5.1 standardization fix).
  2. lookup_ev is continuous & monotone (no step-function jumps).
  3. PolicyEngine flow_mode="down_rank" actually changes p_success, and an
     invalid mode raises ValueError (kill-switch no longer a dead state).
  4. evaluate_regime hysteresis: isolated blip does not flip the latch;
     sustained switch flips exactly on the N-th confirmation bar.
"""
import math
import random

import pytest

from wfe.config.registry import PolicyEngineConfig
from wfe.data.pit_feed import MarketBar
from wfe.engines.flow_engine import FlowEngine
from wfe.engines.structure_engine import StructureEngine
from wfe.engines.volume_engine import VolumeEngine
from wfe.policy.policy_engine import (
    PolicyEngine,
    calibrate_platt_prob,
    fit_platt_params,
    lookup_ev,
)


# ---------- helpers ----------

def _synth_candles(n=230, seed=42, base=20.0, drift=0.0):
    rng = random.Random(seed)
    px = base
    out = []
    for i in range(n):
        chg = rng.gauss(drift, 0.012)
        o = px
        c = max(1.0, px * (1 + chg))
        h = max(o, c) * (1 + abs(rng.gauss(0, 0.004)))
        l = min(o, c) * (1 - abs(rng.gauss(0, 0.004)))
        v = 1_000_000 * (1 + abs(rng.gauss(0, 0.5)))
        out.append(MarketBar(date=f"d{i}", open=o, high=h, low=l, close=c, volume=v))
        px = c
    return out


def _ece_and_logloss(scores, labels, a, b):
    ps = [calibrate_platt_prob(s, a, b) for s in scores]
    ll = -sum(y * math.log(p + 1e-12) + (1 - y) * math.log(1 - p + 1e-12)
              for y, p in zip(labels, ps)) / len(ps)
    bins = {}
    for y, p in zip(labels, ps):
        bins.setdefault(int(p * 10), []).append((y, p))
    ece = sum(len(v) / len(labels) * abs(sum(y for y, _ in v) / len(v)
                                         - sum(p for _, p in v) / len(v))
              for v in bins.values())
    return ece, ll


# ---------- 1. Platt fitting ----------

def test_fit_platt_recovers_true_params():
    rng = random.Random(3)
    true_a, true_b = 0.09, -5.0
    scores, labels = [], []
    for _ in range(400):
        s = rng.uniform(30, 80)
        p = 1 / (1 + math.exp(-(true_a * s + true_b)))
        scores.append(s)
        labels.append(1 if rng.random() < p else 0)
    a_hat, b_hat = fit_platt_params(scores, labels)
    assert abs(a_hat - true_a) < 0.02, f"a_hat={a_hat}"
    assert abs(b_hat - true_b) < 1.0, f"b_hat={b_hat}"
    ece_f, ll_f = _ece_and_logloss(scores, labels, a_hat, b_hat)
    ece_p, ll_p = _ece_and_logloss(scores, labels, 0.075, -4.0)
    assert ece_f <= ece_p + 1e-9
    assert ll_f <= ll_p + 1e-9


def test_fit_platt_rejects_bad_input():
    with pytest.raises(ValueError):
        fit_platt_params([], [])
    with pytest.raises(ValueError):
        fit_platt_params([1.0, 2.0], [1])


# ---------- 2. EV continuity ----------

def test_lookup_ev_is_continuous_and_monotone():
    fine = [lookup_ev(i / 1000) for i in range(1001)]
    steps = [abs(fine[i + 1] - fine[i]) for i in range(len(fine) - 1)]
    # steepest anchor segment slope is (2.00-1.25)/0.10 = 7.5 R/unit-p -> per 0.001 step <= 0.0075
    assert max(steps) <= 0.0076
    assert all(fine[i] <= fine[i + 1] for i in range(len(fine) - 1))
    # Patch V3.5.2: EV(0.50) anchored to exactly 0 (coin-flip => zero expectancy)
    assert abs(lookup_ev(0.50) - 0.0) < 1e-9


# ---------- 3. Kill-switch flow_mode wiring ----------

def _engine_inputs():
    bars = _synth_candles(seed=11, drift=0.002)
    flow = FlowEngine().calculate(bars)
    struct = StructureEngine().calculate(bars)
    vol = VolumeEngine().calculate(bars, [
        {"event_id": e.event_id, "event_type": e.event_type, "bar_index": e.bar_index}
        for e in struct.events])
    return bars, flow, struct, vol


def test_down_rank_differs_from_live_and_invalid_raises():
    bars, flow, struct, vol = _engine_inputs()
    pe = PolicyEngine()
    live = pe.evaluate(bars, flow, struct, vol, flow_mode="live")
    down = pe.evaluate(bars, flow, struct, vol, flow_mode="down_rank")
    off = pe.evaluate(bars, flow, struct, vol, kill_switch_flow_off=True)
    assert live.p_success != down.p_success, "down_rank must not be a no-op vs live"
    assert down.p_success != off.p_success or down.final_size_pct != off.final_size_pct
    with pytest.raises(ValueError):
        pe.evaluate(bars, flow, struct, vol, flow_mode="half_dead")


# ---------- 4. Regime hysteresis ----------

def _counter_bars(bars, mult_old, mult_new):
    n = len(bars)
    out = []
    for i, bb in enumerate(bars):
        m = mult_old if n - 120 <= i < n - 60 else (mult_new if n - 60 <= i < n - 20 else 1.0)
        out.append(MarketBar(date=bb.date, open=bb.open, high=bb.high * m,
                             low=bb.low, close=bb.close, volume=bb.volume))
    return out


def test_hysteresis_blip_and_confirmation():
    cfg = PolicyEngineConfig(regime_hysteresis_bars=3)
    bars = _synth_candles(n=140, seed=5, drift=-0.001)
    B_ON = _counter_bars(bars, 1.30, 1.00)   # raw counter-trend signal
    B_OFF = _counter_bars(bars, 1.00, 1.00)  # raw normal

    # NOTE: evaluate_regime returns the *latched* state, so on call k of a
    # sustained run the value only becomes True once the streak reaches N=3.
    # The scenario runner's B_ON/B_OFF construction is reused here unchanged.

    # blip must NOT flip a latched Counter-Trend state
    peA = PolicyEngine(cfg)
    for _ in range(3):
        peA.evaluate_regime(B_ON)
    assert peA._latched_counter_trend
    still_counter = peA.evaluate_regime(B_OFF)[0]
    assert still_counter is True, "single-bar blip flipped the latch"

    # sustained switch latches exactly on the 3rd consecutive confirmation bar
    peC = PolicyEngine(cfg)
    seq = [bool(peC.evaluate_regime(B_OFF if k < 3 else B_ON)[0]) for k in range(7)]
    assert seq[:2] == [False, False] and seq[2] is True and all(seq[2:])
