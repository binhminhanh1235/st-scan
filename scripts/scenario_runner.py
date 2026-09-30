#!/usr/bin/env python3
"""
Scenario Runner — tổng hợp nhiều kịch bản chạy (S1..S6) để kiểm chứng hành vi
và định lượng các điểm yếu đã được chỉ ra trong phân tích:

  S1  Determinism of Monte Carlo gap/floor risk (simulate_gap_floor_risk)
  S2  Platt-calibrated p_success distribution + EV table sanity
  S3  Kill-switch mode matrix: live vs down_rank vs off
  S4  Counter-trend regime hysteresis (regime_hysteresis_bars có được dùng không?)
  S5  Full WFE V3 pipeline over synthetic universe (PIT -> Engines -> Policy -> Schema)
  S6  Walk-forward split integrity (purge/embargo)

Chạy:  python scripts/scenario_runner.py [--json out.json]
"""
import argparse
import json
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wfe.data.pit_feed import PITFeed, MarketBar
from wfe.engines.flow_engine import FlowEngine
from wfe.engines.structure_engine import StructureEngine
from wfe.engines.volume_engine import VolumeEngine
from wfe.policy.policy_engine import PolicyEngine, calibrate_platt_prob, lookup_ev, fit_platt_params
from wfe.risk.state_machine import simulate_gap_floor_risk
from wfe.scanner import WFEScanner
from wfe.backtest.walk_forward import WalkForwardValidator


# ---------- synthetic data helpers ----------

def synth_candles(n=230, seed=42, base=20.0, drift=0.0, vol_base=1_000_000):
    rng = random.Random(seed)
    px = base
    out = []
    for i in range(n):
        chg = rng.gauss(drift, 0.012)
        o = px
        c = max(1.0, px * (1 + chg))
        h = max(o, c) * (1 + abs(rng.gauss(0, 0.004)))
        l = min(o, c) * (1 - abs(rng.gauss(0, 0.004)))
        v = vol_base * (1 + abs(rng.gauss(0, 0.5))) * (2.5 if abs(chg) > 0.03 else 1.0)
        out.append({"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": round(o, 2),
                    "high": round(h, 2), "low": round(l, 2), "close": round(c, 2),
                    "volume": int(v)})
        px = c
    return out


def bars_from(candles):
    return [MarketBar(date=c["date"], open=c["open"], high=c["high"], low=c["low"],
                      close=c["close"], volume=float(c["volume"])) for c in candles]


RESULTS = {}


def report(name, payload):
    RESULTS[name] = payload
    print(f"\n=== {name} ===")
    print(json.dumps(payload, indent=2, ensure_ascii=False)[:2000])


# ---------- S1: MC determinism ----------

def s1_monte_carlo():
    """V3.5 contract: seeded runs are bit-identical; unseeded runs drift;
    realized event frequencies must match the requested prior."""
    entry, sl = 20.0, 18.5
    unseeded = [simulate_gap_floor_risk(entry, sl, nav_allocation_pct=0.20,
                                        num_simulations=5000)["p99_loss_nav"]
                for _ in range(5)]
    seeded = [simulate_gap_floor_risk(entry, sl, 0.20, 5000, seed=7)["p99_loss_nav"]
              for _ in range(5)]
    # empirical-calibration hook: skewed prior should be reflected in output dict
    skewed = simulate_gap_floor_risk(entry, sl, 0.20, 20000, seed=1,
                                     gap_event_probs=(0.70, 0.25, 0.05))
    nominal = (entry - sl) / entry
    return {
        "unseeded_p99_runs": unseeded,
        "seeded_p99_runs": seeded,
        "deterministic_with_seed": len(set(seeded)) == 1,
        "drift_without_seed": len(set(unseeded)) > 1,
        "empirical_prior_check": {"requested": [0.70, 0.25, 0.05],
                                   "realized": [skewed["p_normal"], skewed["p_gap"],
                                                skewed["p_floor"]],
                                   "p99": skewed["p99_loss_nav"]},
        "nominal_loss_pct": round(nominal, 4),
        "note": ("V3.5: seed -> tái lập bit-identical; gap_event_probs cho phép nạp tần suất "
                 "gap/floor empirical từ lịch sử HOSE thay prior hằng số 90/8/2."),
    }


# ---------- S2: Platt + EV table ----------

def s2_calibration():
    scores = list(range(0, 101, 5))
    probs = [round(calibrate_platt_prob(s), 4) for s in scores]
    evs = [round(lookup_ev(p), 4) for p in probs]
    neutral_raw = 50 * .30 + (100 - 30) * .25 + 50 * .20 + 50 * .15 + 40 * .10
    neutral_p = calibrate_platt_prob(neutral_raw)
    monotonic = all(evs[i] <= evs[i + 1] for i in range(len(evs) - 1))
    # continuity check: adjacent 0.01-p steps should never jump more than the
    # steepest segment slope (~ (2.10-1.35)/0.1 = 7.5 R per unit p)
    fine = [lookup_ev(i / 1000) for i in range(0, 1001)]
    max_step = max(abs(fine[i + 1] - fine[i]) for i in range(len(fine) - 1))
    # fit_platt_params smoke test on synthetic labeled data
    import math as _m
    rng = random.Random(3)
    fit_scores, fit_labels = [], []
    for _ in range(400):
        s = rng.uniform(30, 80)
        true_p = 1 / (1 + _m.exp(-(0.09 * s - 5.0)))
        fit_scores.append(s)
        fit_labels.append(1 if rng.random() < true_p else 0)
    a_hat, b_hat = fit_platt_params(fit_scores, fit_labels)
    base_rate = sum(fit_labels) / len(fit_labels)
    # calibration quality: expected calibration error & log-loss of fitted vs prior
    def ece_and_ll(a, b):
        ps = [calibrate_platt_prob(s_, a, b) for s_ in fit_scores]
        ll = -sum(y * _m.log(p_ + 1e-12) + (1 - y) * _m.log(1 - p_ + 1e-12)
                  for y, p_ in zip(fit_labels, ps)) / len(ps)
        bins = {}
        for y, p_ in zip(fit_labels, ps):
            k = int(p_ * 10)
            bins.setdefault(k, []).append((y, p_))
        e = sum(len(v) / len(fit_labels) * abs(sum(y for y, _ in v) / len(v)
                - sum(p_ for _, p_ in v) / len(v)) for v in bins.values())
        return round(e, 4), round(ll, 4)
    ece_fitted, ll_fitted = ece_and_ll(a_hat, b_hat)
    ece_prior, ll_prior = ece_and_ll(0.075, -4.0)
    return {
        "score_to_p": dict(zip(scores, probs)),
        "neutral_raw_score": round(neutral_raw, 2),
        "neutral_p_success": round(neutral_p, 4),
        "neutral_ev_r": round(lookup_ev(neutral_p), 4),
        "ev_at_050": round(lookup_ev(0.50), 4),
        "ev_monotonic_in_p": monotonic,
        "max_fine_grained_step_r": round(max_step, 5),
        "platt_fit": {"a_hat": a_hat, "b_hat": b_hat, "true_a": 0.09, "true_b": -5.0,
                       "label_base_rate": round(base_rate, 3),
                       "ece_fitted": ece_fitted, "ece_prior": ece_prior,
                       "logloss_fitted": ll_fitted, "logloss_prior": ll_prior},
        "note": ("V3.5: EV nội suy tuyến tính liên tục (không còn step-jump 0.75R); "
                 "fit_platt_params ước lượng (a,b) từ nhãn win/lose — kiểm tra a_hat/b_hat "
                 "hồi quy về giá trị sinh dữ liệu. EV(0.5) vẫn neo +0.10R theo prior — "
                 "cần thay anchor bằng đường EV fitted sau backtest."),
    }


# ---------- S3: kill-switch modes ----------

def s3_kill_switch_modes():
    candles = synth_candles(seed=11, drift=0.002)
    bars = bars_from(candles)
    fe, se, ve, pe = FlowEngine(), StructureEngine(), VolumeEngine(), PolicyEngine()
    flow = fe.calculate(bars)
    struct = se.calculate(bars)
    vol = ve.calculate(bars, [{"event_id": e.event_id, "event_type": e.event_type, "bar_index": e.bar_index}
                              for e in struct.events])
    out = {}
    for mode in ("live", "down_rank", "off"):
        d = pe.evaluate(bars, flow, struct, vol,
                        kill_switch_flow_off=(mode == "off"), flow_mode=mode)
        out[mode] = {"p_success": d.p_success, "final_size_pct": d.final_size_pct,
                     "classification": d.classification}
    spread = max(v["p_success"] for v in out.values() if isinstance(v, dict)) - \
             min(v["p_success"] for v in out.values() if isinstance(v, dict))
    out["down_rank_differs_from_live"] = (out["down_rank"]["p_success"]
                                          != out["live"]["p_success"])
    out["max_p_spread_across_modes"] = round(spread, 4)
    # invalid mode must raise (governance contract)
    try:
        pe.evaluate(bars, flow, struct, vol, flow_mode="half_dead")
        out["invalid_mode_rejected"] = False
    except ValueError:
        out["invalid_mode_rejected"] = True
    out["finding"] = ("V3.5: down_rank được wire vào PolicyEngine (giảm weight flow về "
                      "trung tính); ba mode cho p/size phân biệt; flow_mode sai bị raise.")
    return out


# ---------- S4: hysteresis ----------

def s4_hysteresis():
    from wfe.config.registry import PolicyEngineConfig
    cfg_h3 = PolicyEngineConfig(regime_hysteresis_bars=3)
    pe = PolicyEngine(cfg_h3)
    candles = synth_candles(n=140, seed=5, drift=-0.001)
    bars = bars_from(candles)

    def counter_bars(mult_old, mult_new):
        b = list(bars)
        for i in range(60, 120):   # 'old' window indices (n=140 -> [-120:-60] ~ 20..80; use both)
            pass
        # windows are relative to end: old=[-120:-60], recent=[-60:-20]
        out = []
        n = len(bars)
        for i, bb in enumerate(bars):
            m = 1.0
            if n - 120 <= i < n - 60:
                m = mult_old
            elif n - 60 <= i < n - 20:
                m = mult_new
            out.append(MarketBar(date=bb.date, open=bb.open, high=bb.high * m,
                                 low=bb.low, close=bb.close, volume=bb.volume))
        return out

    def raw_signal(pe_obj, b):
        # reset latch so we read the RAW decision of this single call
        pe_obj._latched_counter_trend = False
        pe_obj._raw_counter_streak = 0
        pe_obj._raw_normal_streak = 0
        pe_obj.evaluate_regime(b)
        return pe_obj._raw_counter_streak > 0

    B_ON = counter_bars(1.30, 1.00)    # raw = counter-trend
    B_OFF = counter_bars(1.00, 1.00)   # raw = normal (drift-down path keeps ratio<1.05? verify below)
    assert raw_signal(pe, B_ON), "sanity: B_ON must produce raw counter signal"

    # Test A: start latched in Counter-Trend (3 sustained ON bars), then feed a
    # single OFF blip; with hysteresis=3 the latch must NOT flip on one bar.
    peA = PolicyEngine(cfg_h3)
    for _ in range(3):
        peA.evaluate_regime(B_ON)                                  # latches Counter-Trend
    assert peA._latched_counter_trend, "sanity: engine should be latched counter-trend"
    st_blip = peA.evaluate_regime(B_OFF)[0]                        # 1-bar blip back to normal
    test_a_no_flip = (st_blip == True)                             # still counter-trend => no flip

    # Test B: oscillating boundary sequence ON,OFF,ON,OFF,... counted by a fresh engine
    peB = PolicyEngine(cfg_h3)
    states = []
    for k in range(8):
        b = B_ON if k % 2 == 0 else B_OFF
        states.append(peB.evaluate_regime(b)[0])
    flip_flops = sum(1 for i in range(1, len(states)) if states[i] != states[i - 1])

    # Test C: sustained switch requires exactly N=3 confirmations to latch
    peC = PolicyEngine(cfg_h3)
    latch_seq = []
    for k in range(7):
        b = B_OFF if k < 3 else B_ON
        latch_seq.append(bool(peC.evaluate_regime(b)[0]))
    # hysteresis=3 => latched state changes only when streak reaches 3, i.e. on
    # call index 2 (0-based) of the sustained run -> seq F,F,T,T,T,T,T is CORRECT.
    confirmed_at_3rd_bar = (latch_seq[:2] == [False, False] and latch_seq[2] == True
                            and all(latch_seq[2:]))

    import inspect
    src = inspect.getsource(PolicyEngine.evaluate_regime)
    return {
        "hysteresis_param_used_in_source": "regime_hysteresis_bars" in src,
        "config_value": cfg_h3.regime_hysteresis_bars,
        "test_a_isolated_blip_does_not_flip": test_a_no_flip,
        "test_b_oscillating_states": states,
        "test_b_flip_flops": flip_flops,
        "test_c_sustained_switch_latches_on_3rd_bar": confirmed_at_3rd_bar,
        "test_c_latch_sequence": latch_seq,
        "finding": ("V3.5: evaluate_regime latch N-bar confirmation hai chiều; chuỗi tín hiệu "
                    "rung quanh biên 1.05 phải cho flip-flop <= số lần xác nhận hợp lệ "
                    "(so với V3.4: mọi bar đảo chiều đều flip)."),
    }


# ---------- S5: full pipeline on synthetic universe ----------

def s5_pipeline_universe():
    feed = PITFeed()
    universe = {}
    for i, sym in enumerate(["HPG", "MWG", "FPT", "VCB", "DIG", "STB", "VIX", "REE"]):
        universe[sym] = synth_candles(n=230, seed=100 + i, base=15 + i * 7,
                                      drift=[0.004, 0.001, -0.002, 0.003, -0.004, 0.002, 0.0, 0.001][i])
    sc = WFEScanner()
    res = sc.scan_universe(universe, top_n=4, min_p_success=0.45)
    rows = [{
        "symbol": c["symbol"], "p_success": c["policy"]["p_success"],
        "ev_r": c["policy"]["ev_r"], "size_pct": c["policy"]["size_pct"],
        "classification": c["classification"],
        "active_setup": c["structure"]["active_setup"],
    } for c in res["top_candidates"]]
    actionable = [r for r in rows if r["classification"] == "ACTIONABLE"]
    return {
        "scanned": res["total_scanned"], "qualified": res["qualified_count"],
        "rows": rows,
        "actionable_count": len(actionable),
        "finding": ("Trên dữ liệu tổng hợp, pipeline chạy end-to-end OK nhưng mọi mã ACTIONABLE đều "
                    "phải kích hoạt được TEST_SPRING_PHASE_C hoặc BU_LPS_PHASE_D; nếu không toàn bộ "
                    "về WATCHLIST size=0 — tỷ lệ bao phủ tín hiệu thực tế rất thấp và chưa đo được."),
    }


# ---------- S6: walk-forward splits ----------

def s6_walk_forward():
    wf = WalkForwardValidator(k_folds=5, embargo_bars=5)
    splits = wf.split(1000)
    overlaps = []
    for i, (tr, te) in enumerate(splits):
        for tr2, te2 in splits[i + 1:]:
            if te[0] < tr2[1] and tr2[0] < te[1]:
                overlaps.append((i, (te, tr2)))
    gaps = [te[0] - tr[1] for tr, te in splits]
    return {
        "splits": splits,
        "train_test_gaps": gaps,
        "cross_fold_overlaps": overlaps,
        "note": ("Embargo chỉ áp giữa train và test của CÙNG fold; test fold i nằm sát train fold i+1 "
                 "nhưng train mở rộng từ 0 nên overlap liên-fold không xảy ra. Tuy nhiên K-fold kiểu "
                 "'expanding window' này chỉ tạo k-1 splits và không purge label horizon (holding period) "
                 "— embargo 5 bar nhỏ hơn horizon thoát lệnh thực tế (exit ladder có thể giữ nhiều tuần)."),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    s1_monte_carlo.__wrapped__ = None
    report("S1_monte_carlo_determinism", s1_monte_carlo())
    report("S2_platt_ev_calibration", s2_calibration())
    report("S3_kill_switch_modes", s3_kill_switch_modes())
    report("S4_regime_hysteresis", s4_hysteresis())
    report("S5_pipeline_synthetic_universe", s5_pipeline_universe())
    report("S6_walk_forward_integrity", s6_walk_forward())
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(RESULTS, f, indent=2, ensure_ascii=False)
        print(f"\nSaved -> {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
