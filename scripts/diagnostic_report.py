#!/usr/bin/env python3
"""
VNStock WFE V3.5 — Full Diagnostic Report Generator (one-shot)
===============================================================
Chay MOT LENH, thu thap TOAN BO thong tin can thiet de danh gia toan dien:

  [0] Moi truong (Python/OS/packages/file cau truc) + dieu kien tien quyet
  [1] Toan bo unit test (pytest) — pass/fail tung test
  [2] S1 Monte Carlo determinism: in-process + CROSS-PROCESS seed reproducibility
  [3] S2 Calibration: Platt curve, EV monotonicity, EV(0.5) anchor, neutral-score EV
  [4] S3 Kill-switch matrix: live vs down_rank vs off (delta p & size)
  [5] S4 Regime hysteresis: flip-flop suppression tren chuoi rung bien
  [6] S5 Pipeline end-to-end TREN DU LIEU THAT (HOSE/Yahoo): coverage,
      p/EV/sizing distribution, empirical gap/floor frequencies
  [7] S6 Walk-forward split integrity (embargo vs holding horizon)
  [8] Legacy bridge smoke: import vnstock_server + classify_vpa

Ket qua dua ra man hinh VA luu vao:
    diagnostic_report.txt   (log doc cho nguoi/AI)
    diagnostic_results.json (so lieu day du tung ticker)
=> GUI CA 2 FILE NAY de nhan phan tich toan dien.

Windows 10 (cmd):   cd <repo> && py -3 scripts\diagnostic_report.py
macOS/Linux:        python3 scripts/diagnostic_report.py
Options:            --no-network | --universe-size N | --days Y | --offline-universe
Exit code: 0 hoan thanh, 2 thieu tien quyet (in lenh fix kem theo).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
import traceback
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

IS_WINDOWS = platform.system() == "Windows"
if IS_WINDOWS:
    # Console mac dinh cp1252 -> crash vi ky tu dac biet; ep UTF-8 output.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        os.environ.setdefault("PYTHONUTF8", "1")
    except Exception:
        pass

REPORT_PATH = REPO_ROOT / "diagnostic_report.txt"
JSON_PATH = REPO_ROOT / "diagnostic_results.json"
LIVE_CACHE = REPO_ROOT / "scripts" / "real_data_cache.json"
OFFLINE_UNIVERSE = REPO_ROOT / "wfe" / "ops" / "offline_universe.json"

REPORT_LINES: list[str] = []
RESULTS_JSON: dict = {"meta": {}, "checks": {}}


def emit(line: str = "") -> None:
    print(line)
    REPORT_LINES.append(line)


def section(title: str) -> None:
    emit("")
    emit("=" * 78)
    emit(f"  {title}")
    emit("=" * 78)


def record(cid: str, data: dict) -> None:
    RESULTS_JSON["checks"][cid] = data


# ----------------------------------------------------------------------
# [0] Environment
# ----------------------------------------------------------------------
def check_environment() -> bool:
    section("[0/8] MOI TRUONG & DIEU KIEN TIEN QUYET")
    ok = True
    emit(f"  Python   : {sys.version.split()[0]}")
    emit(f"  Platform : {platform.system()} {platform.release()} ({platform.machine()})")
    emit(f"  Repo root: {REPO_ROOT}")
    emit(f"  Time UTC : {datetime.now(timezone.utc).isoformat()}")

    if sys.version_info < (3, 10):
        emit(f"  [FAIL] Python >= 3.10 required (duoc {sys.version_info.major}.{sys.version_info.minor})")
        ok = False
    else:
        emit("  [OK]   Python >= 3.10")

    for pkg in ("numpy", "pandas"):
        try:
            m = __import__(pkg)
            emit(f"  [OK]   {pkg} {getattr(m, '__version__', '?')}")
        except ImportError:
            emit(f"  [FAIL] thieu {pkg} -> py -3 -m pip install {pkg}")
            ok = False

    for pkg in ("scipy", "pytest"):
        try:
            m = __import__(pkg)
            emit(f"  [OK]   {pkg} {getattr(m, '__version__', '?')} (optional)")
        except ImportError:
            emit(f"  [WARN] thieu {pkg} -> py -3 -m pip install {pkg} (can cho mot so check)")

    key_files = [
        "wfe/scanner.py", "wfe/data/pit_feed.py", "wfe/risk/state_machine.py",
        "wfe/policy/policy_engine.py", "wfe/backtest/walk_forward.py",
        "wfe/config/registry.py", "wfe/output/schema.py", "mcp/vnstock_server.py",
    ]
    missing = [f for f in key_files if not (REPO_ROOT / f).exists()]
    if missing:
        emit(f"  [FAIL] thieu file pipeline: {missing}")
        ok = False
    else:
        emit(f"  [OK]   du {len(key_files)} file cot loi")

    emit("  [INFO] Neu pytest bao 'ImportPathNotSetError': set PYTEST_DISABLE_PLUGIN_AUTOLOAD=1")
    record("env", {"python": sys.version.split()[0], "platform": platform.platform(),
                   "ok": ok, "missing_files": missing})
    return ok


# ----------------------------------------------------------------------
# [1] Unit tests
# ----------------------------------------------------------------------
def run_test_suite() -> dict:
    section("[1/8] UNIT TEST SUITE (pytest -q)")
    summary = {"ran": False, "passed": 0, "failed": 0, "errors": 0,
               "failures_detail": [], "tail": ""}
    try:
        import pytest  # noqa: F401
    except ImportError:
        emit("  [SKIP] pytest chua cai dat -> py -3 -m pip install pytest")
        record("tests", summary)
        return summary

    t0 = time.time()
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line", "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=900, env=env,
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    tail = "\n".join(out.strip().splitlines()[-30:])
    m = re.search(r"(\d+) failed", out)
    p = re.search(r"(\d+) passed", out)
    e = re.search(r"(\d+) error", out)
    if m or p:
        summary.update(ran=True,
                       failed=int(m.group(1)) if m else 0,
                       passed=int(p.group(1)) if p else 0,
                       errors=int(e.group(1)) if e else 0)
    summary["failures_detail"] = [x.group(1) for x in re.finditer(r"FAILED (\S+)", out)][:30]
    summary["duration_s"] = round(time.time() - t0, 1)
    summary["tail"] = tail

    if summary["ran"]:
        status = "[OK]" if not summary["failed"] and not summary["errors"] else "[FAIL]"
        emit(f"  {status} passed={summary['passed']} failed={summary['failed']} "
             f"errors={summary['errors']} ({summary['duration_s']}s)")
        for f in summary["failures_detail"]:
            emit(f"      - {f}")
        if summary["failed"] or summary["errors"]:
            emit("  --- 30 dong cuoi pytest output ---")
            for ln in tail.splitlines():
                emit(f"      {ln}")
    else:
        emit("  [FAIL] khong parse duoc ket qua pytest — output goc:")
        for ln in tail.splitlines():
            emit(f"      {ln}")
    record("tests", summary)
    return summary


# ----------------------------------------------------------------------
# [2] S1 determinism
# ----------------------------------------------------------------------
def check_determinism() -> None:
    section("[2/8] S1 — MONTE CARLO DETERMINISM (in-proc + cross-proc)")
    from wfe.risk.state_machine import simulate_gap_floor_risk
    d1 = simulate_gap_floor_risk(entry_price=25000, sl=24000, seed=42, num_simulations=2000)
    d2 = simulate_gap_floor_risk(entry_price=25000, sl=24000, seed=42, num_simulations=2000)
    same_inproc = json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True)
    emit(f"  [ {'OK' if same_inproc else 'FAIL'} ] in-process seed=42 x2 identical: {same_inproc}")

    snippet = (
        "import json,sys;sys.path.insert(0,%r);"
        "from wfe.risk.state_machine import simulate_gap_floor_risk;"
        "print(json.dumps(simulate_gap_floor_risk(entry_price=25000,sl=24000,seed=42,"
        "num_simulations=2000),sort_keys=True))" % str(REPO_ROOT)
    )
    hashes = []
    for _ in range(2):
        pr = subprocess.run([sys.executable, "-c", snippet], capture_output=True,
                            text=True, timeout=180)
        hashes.append(hash(pr.stdout.strip()))
    cross_ok = len(set(hashes)) == 1 and hashes[0] != hash("")
    emit(f"  [ {'OK' if cross_ok else 'FAIL'} ] cross-process seed=42 reproducible: {cross_ok}")

    d3 = simulate_gap_floor_risk(entry_price=25000, sl=24000, seed=7, num_simulations=2000)
    diff_ok = json.dumps(d1, sort_keys=True) != json.dumps(d3, sort_keys=True)
    emit(f"  [ {'OK' if diff_ok else 'WARN'} ] different seeds differ (full result): {diff_ok}")
    emit(f"  sample(seed=42): {d1}")
    # Do lap lai cua CHINH P99 khi tang n: p99(n=2000) la quantile mau thu 20 tu
    # duoi => chi ~80% truong hop lap lai khi chay n=20000. Day la do TINH ON DINH
    # cua uoc luong p99 (khac voi determinism). So sanh bang nhieu seed.
    import statistics as _st
    q99_2k = [simulate_gap_floor_risk(entry_price=25000, sl=24000, seed=s,
                                      num_simulations=2000)["p99_loss_nav"] for s in range(10)]
    q99_20k = [simulate_gap_floor_risk(entry_price=25000, sl=24000, seed=s,
                                       num_simulations=20000)["p99_loss_nav"] for s in range(10)]
    same_frac = sum(1 for a, b in zip(q99_2k, q99_20k) if a == b) / len(q99_2k)
    emit(f"  [INFO] p99 tai n=2000 trung voi n=20000 cung seed: {same_frac:.0%} "
         f"(nho n -> uoc luong p99 NHIEU; spread n=2k {_st.pstdev(q99_2k):.4f} vs n=20k {_st.pstdev(q99_20k):.4f})")
    emit("       => Neu can so lieu dau vao gap/floor on dinh, dung n>=20000 hoac "
         "tail-analytic thay vi p99 mau")
    bad_freq = abs(d1["p_normal"] + d1["p_gap"] + d1["p_floor"] - 1.0) > 1e-6
    emit(f"  [ {'WARN' if bad_freq else 'OK'} ] realized freqs sum to 1.0")
    record("s1_determinism", {"in_process_reproducible": same_inproc,
                              "cross_process_reproducible": cross_ok,
                              "seeds_differ": diff_ok, "sample": d1,
                              "p99_n2000_samples": q99_2k, "p99_n20000_samples": q99_20k,
                              "p99_stability_frac": same_frac})


# ----------------------------------------------------------------------
# [3] S2 calibration
# ----------------------------------------------------------------------
def check_calibration() -> None:
    section("[3/8] S2 — CALIBRATION (Platt curve / EV monotonicity / anchor)")
    from wfe.policy.policy_engine import (PolicyEngine, PolicyEngineConfig,
                                          lookup_ev, calibrate_platt_prob,
                                          fit_platt_params)
    eng = PolicyEngine(PolicyEngineConfig())
    a = getattr(eng.config, "platt_a", 0.075)
    b = getattr(eng.config, "platt_b", -4.0)
    rows, prev_ev, viol = [], None, 0
    for s in range(30, 76, 5):
        p = calibrate_platt_prob(s, a, b)
        ev = lookup_ev(p)
        flag = ""
        if prev_ev is not None and ev < prev_ev - 1e-12:
            viol += 1
            flag = "<- NON-MONOTONIC"
        prev_ev = ev
        rows.append({"score": s, "p": round(p, 4), "ev_R": round(ev, 4)})
        emit(f"    score={s:>3}  p={p:.4f}  EV={ev:+.3f}R {flag}")
    ev_half = lookup_ev(0.5)
    anchor_ok = abs(ev_half) < 0.05
    emit(f"  [ {'OK' if anchor_ok else 'FAIL'} ] EV(0.5)={ev_half:+.4f}R (can gan 0)")
    p_neutral = calibrate_platt_prob(54, a, b)
    ev_neutral = lookup_ev(p_neutral)
    warn = "" if ev_neutral <= 0 else " <-- trung tinh van CONG EV (phai bi loc tru khi cap von)"
    emit(f"  score 54 -> p={p_neutral:.4f}, EV={ev_neutral:+.3f}R{warn}")
    fit_note = "n/a"
    fit_ok = None
    try:
        import random
        rng = random.Random(0)
        scores = [rng.uniform(30, 80) for _ in range(400)]
        labels = [1 if sc > 58 + rng.gauss(0, 5) else 0 for sc in scores]
        a_fit, b_fit = fit_platt_params(scores, labels)
        p_lo, p_hi = calibrate_platt_prob(40, a_fit, b_fit), calibrate_platt_prob(75, a_fit, b_fit)
        fit_ok = p_hi > p_lo and 0 < p_lo < 1
        fit_note = f"a={a_fit:.4f} b={b_fit:.4f} p(40)={p_lo:.3f} p(75)={p_hi:.3f}"
        emit(f"  [ {'OK' if fit_ok else 'FAIL'} ] fit_platt_params tren nhan synthetic: {fit_note}")
    except Exception as ex:
        emit(f"  [ERROR] fit_platt_params: {ex}")
        fit_note = f"ERROR {ex}"
    emit(f"  monotonicity violations: {viol}")
    record("s2_calibration", {"curve": rows, "ev_at_050": ev_half, "anchor_ok": anchor_ok,
                              "neutral_score_54": {"p": p_neutral, "ev": ev_neutral},
                              "monotonic_violations": viol, "fit_check": fit_note,
                              "fit_ok": fit_ok})


# ----------------------------------------------------------------------
# [4] S3 kill-switch (qua scanner that, dung offline universe cua repo)
# ----------------------------------------------------------------------
def check_killswitch() -> None:
    section("[4/8] S3 — KILL-SWITCH MATRIX (live/down_rank/off)")
    out = {}
    try:
        from wfe.policy.policy_engine import PolicyEngine, PolicyEngineConfig
        from wfe.data.pit_feed import MarketBar  # Patch: import tai day (NameError fix)
        # Deterministic feature row via monkeypatched engines -> so delta p/size
        # do đo duoc dung che kill-switch, khong bi nhieu boi setup gate.
        class _V:  # generic value holder
            def __init__(self, v): self.value = v
        class _Flow:
            data_ok = True
            accum, dist, trend = _V(90.0), _V(10.0), _V(85.0)
            trend_collapse_warning = False
        class _Struct:
            data_ok = True
            events = []
            phase_prob = {"C": 0.6, "D": 0.7}
            active_setup = "BU_LPS_PHASE_D"
            is_box_unstable = False
            diagnostics = {}
            class levels:
                t1, t2, tr_high, tr_mid, tr_low, major_supply, event_low = 30.0, 35.0, 26.0, 24.0, 20.0, 40.0, 22.0
                t1_valid, target_tag = True, "[NORMAL]"
        class _Vol:
            data_ok = True
            event_qualities = {}
            rvol = 2.0
        bars = [MarketBar(date=f"d{i}", open=25, high=25.5, low=24.5, close=25.0, volume=1e6)
                for i in range(130)]
        for mode in ("live", "down_rank", "off"):
            eng = PolicyEngine(PolicyEngineConfig())
            dec = eng.evaluate(bars, _Flow(), _Struct(), _Vol(),
                               kill_switch_flow_off=(mode == "off"), flow_mode=mode)
            out[mode] = {"classification": dec.classification,
                         "p_success": round(dec.p_success, 4),
                         "ev_r": round(dec.ev_r, 3),
                         "size_pct": round(dec.final_size_pct, 2)}
            emit(f"    {mode:<10}: {out[mode]}")
        dl = abs(out["live"]["p_success"] - out["down_rank"]["p_success"])
        do = abs(out["live"]["p_success"] - out["off"]["p_success"])
        sz_dl = abs(out["live"]["size_pct"] - out["down_rank"]["size_pct"])
        # Patch V3.6 (C.1): tieu chi "co hieu luc" PHAI la cat von, khong chi cat diem.
        # Thuoc do tren may user: p delta 0.09 nhung size delta = 0.00% -> van PASS
        # "CO Y NGHIA" (governance rong). Nay size_delta >= 1.0% la dieu kien CAN.
        size_ratio = (out["down_rank"]["size_pct"] / out["live"]["size_pct"]
                      if out["live"]["size_pct"] > 0 else 1.0)
        eff = sz_dl >= 1.0 and size_ratio <= 0.75
        tag = "CO Y NGHIA (size bi cat)" if eff else ("KHONG CAT VON (governance rong!)" if dl > 1e-6 else "KHONG TAC DUNG (dead state!)")
        emit(f"  [ {'OK' if eff else 'FAIL'} ] delta p live->down_rank={dl:.4f}, "
             f"size delta={sz_dl:.2f}% (ratio={size_ratio:.2f}) [{tag}]")
        emit(f"      delta p live->off={do:.4f}")
        record("s3_killswitch", {"matrix": out, "delta_live_downrank_p": dl,
                                 "delta_live_off_p": do, "delta_size": sz_dl,
                                 "size_ratio_downrank_vs_live": round(size_ratio, 3),
                                 "effective": eff})
    except Exception as ex:
        emit(f"  [ERROR] {type(ex).__name__}: {ex}")
        emit(traceback.format_exc()[-800:])
        record("s3_killswitch", {"error": str(ex)[:300]})


# ----------------------------------------------------------------------
# [5] S4 regime hysteresis
# ----------------------------------------------------------------------
def check_hysteresis() -> None:
    section("[5/8] S4 — REGIME HYSTERESIS (chong flip-flop)")
    try:
        from wfe.policy.policy_engine import PolicyEngine, PolicyEngineConfig
        from wfe.data.pit_feed import MarketBar
        eng = PolicyEngine(PolicyEngineConfig())

        def mk_bar(i, high):  # close/vol co dinh, chi dao High de dua raw signal
            return MarketBar(date=f"2023-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
                             open=100.0, high=high, low=99.0, close=100.0, volume=1e6)

        bars = []
        states = []
        # Phase A: 170 bar -> raw Counter-Trend ON (peak_old >> peak_new).
        # FIX V3.5.2: du lieu FLAT khong the kich hoat regime nay (max==max => ratio=1.0).
        # Window tai bar i (i>=120): old=[i-120,i-60), recent=[i-60,i-20), bar moi nhat o ngoai.
        # Dat spike HIGH=150 tai bar [40,60) va [150,170), base=120 con lai:
        #   - i trong [160,170): spike nam giua old-window => peak_old=150; recent hoan toan
        #     base => peak_new=120 => ratio 1.25 > 1.05 => raw ON (10 bar cuoi A).
        #   - Phase B/C bar HIGH=100: spike [150,170) roi dan sang recent-window => raw OFF;
        #     close fallback cung OFF vi spike chi o HIGH (close=100). Sau >=3 bar OFF => latch flip.
        for i in range(170):
            h = 150.0 if (40 <= i < 60 or 150 <= i < 170) else 120.0
            bars.append(mk_bar(i, h))
            _, flag, _ = eng.evaluate_regime(bars)
            states.append(flag)
        on_before = sum(1 for s in states[-10:] if "Counter" in s)
        # Phase B: chen 2 bar rung NGAN duoi nguong (raw OFF) — phai KHONG flip latch
        for j in range(2):
            bars.append(mk_bar(170 + j, 100.0))
            _, flag, _ = eng.evaluate_regime(bars)
            states.append(flag)
        flipped_early = any("Normal" in s for s in states[-2:])
        # Phase C: them >= hysteresis_bars bar thap lien tiep -> latch PHAI flip
        n_confirm = max(1, int(getattr(eng.config, "regime_hysteresis_bars", 3)))
        for j in range(n_confirm + 1):
            bars.append(mk_bar(172 + j, 100.0))
            _, flag, _ = eng.evaluate_regime(bars)
            states.append(flag)
        flipped_late = "Normal" in states[-1]

        emit(f"    last states: {states[-6:]}")
        emit(f"  [ {'OK' if on_before == 10 else 'FAIL'} ] latch ON sau giai doan counter-trend dai")
        emit(f"  [ {'OK' if not flipped_early else 'FAIL'} ] 2 bar rung < hysteresis_bar({n_confirm}) KHONG flip: {not flipped_early}")
        emit(f"  [ {'OK' if flipped_late else 'FAIL'} ] du >= {n_confirm} bar xac nhan thi flip: {flipped_late}")
        ok = on_before == 10 and (not flipped_early) and flipped_late
        record("s4_hysteresis", {"latched_on": on_before, "short_noise_flip": flipped_early,
                                 "confirmed_flip": flipped_late, "pass": ok})
    except Exception as ex:
        emit(f"  [ERROR] {type(ex).__name__}: {ex}")
        record("s4_hysteresis", {"error": str(ex)[:300]})


# ----------------------------------------------------------------------
# [6] S5 real-data pipeline
# ----------------------------------------------------------------------
UNIVERSE_LARGE = ["HPG", "VCB", "VNM", "FPT", "SSI", "HCM", "VND", "STB", "MBB",
                  "ACB", "TPB", "CTG", "GVR", "VCI", "SHB", "DGC", "PNJ", "REE"]
UNIVERSE_SMALL = ["MKP", "APG", "SVI", "HVT", "QBS", "L35", "SBC", "VNE", "HHS", "KSA"]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch_yahoo(ticker: str, days: int):
    """Yahoo chart API -> list candle dicts (khong can yfinance)."""
    rng = {365: "1y", 730: "2y", 1095: "3y", 1825: "5y"}.get(days, "2y")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}.VN?range={rng}&interval=1d"
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=25) as resp:
            payload = json.loads(resp.read().decode())
        result = payload["chart"]["result"][0]
        ts = result.get("timestamp") or []
        q = result["indicators"]["quote"][0]
        out = []
        for i, t in enumerate(ts):
            o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
            if None in (o, h, l, c, v) or float(v) <= 0:
                continue
            d = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
            out.append({"date": d, "open": float(o), "high": float(h),
                        "low": float(l), "close": float(c), "volume": float(v)})
        return out if len(out) >= 80 else None
    except Exception:
        return None


def empirical_limit_stats(candles):
    n_gap_down = n_floor = 0
    prev_c = None
    for cd in candles:
        if prev_c:
            ret = cd["close"] / prev_c - 1
            if cd["open"] / prev_c - 1 <= -0.02:
                n_gap_down += 1
            if ret <= -0.0695:
                n_floor += 1
        prev_c = cd["close"]
    n = max(len(candles) - 1, 1)
    return {"gap_down_freq": round(n_gap_down / n, 4), "floor_freq": round(n_floor / n, 4)}


def check_pipeline_real_data(universe_size: int, days: int, allow_network: bool,
                             force_offline: bool) -> None:
    section(f"[6/8] S5 — PIPELINE TREN DU LIEU THAT (HOSE, toi da {universe_size} ma)")
    out = {"source": None, "attempted": 0, "loaded": 0, "actionable": 0,
           "watchlist": 0, "reserve": 0, "rejected": 0, "per_ticker": [],
           "empirical": {}, "notes": []}
    dfs: dict = {}
    source = None

    if allow_network and not force_offline:
        tickers = (UNIVERSE_LARGE + UNIVERSE_SMALL)[:universe_size]
        for t in tickers:
            out["attempted"] += 1
            cs = fetch_yahoo(t, days)
            if cs is None:
                emit(f"    {t:<6} download FAIL/<80 bars")
                continue
            dfs[t] = cs
            out["loaded"] += 1
            st = empirical_limit_stats(cs)
            emit(f"    {t:<6} {len(cs):>4} bars  close={cs[-1]['close']:.0f}  "
                 f"gap_down={st['gap_down_freq']:.3f} floor={st['floor_freq']:.4f}")
        if dfs:
            source = "yahoo-live"
            try:  # persist cache => co the gui file nay thay tai tai chay live
                LIVE_CACHE.write_text(json.dumps(dfs), encoding="utf-8")
                out["notes"].append(f"cached raw data -> {LIVE_CACHE.name}")
            except Exception:
                pass
        else:
            out["notes"].append("yahoo live fail (firewall/rate-limit)")
            emit("  [WARN] khong tai duoc Yahoo — thu chay lai sau hoac gui cache may khac")

    if not dfs and LIVE_CACHE.exists() and not force_offline:
        dfs = json.loads(LIVE_CACHE.read_text(encoding="utf-8"))
        out["loaded"] = len(dfs)
        source = "cache(real_data_cache.json)"
        emit(f"  dung CACHE du lieu that: {LIVE_CACHE.name} ({len(dfs)} ma)")
    if not dfs and OFFLINE_UNIVERSE.exists():
        dfs = json.loads(OFFLINE_UNIVERSE.read_text(encoding="utf-8"))
        out["loaded"] = len(dfs)
        source = "offline-synthetic"
        emit("  dung OFFLINE synthetic universe — ket qua S5 KHONG phai du lieu that!")

    if not dfs:
        out["notes"].append("khong co du lieu nao de chay pipeline")
        emit("  [FAIL] khong co du lieu -> kiem tra mang hoac copy real_data_cache.json")
        record("s5_real_pipeline", out)
        return
    out["source"] = source

    from wfe.scanner import WFEScanner
    from wfe.policy.policy_engine import lookup_ev
    scan = WFEScanner()
    ps, evs, actionables = [], [], []
    for sym, cs in dfs.items():
        try:
            res = scan.analyze_symbol(sym, cs)
        except Exception as ex:
            emit(f"    {sym} SCAN ERROR: {type(ex).__name__}: {str(ex)[:150]}")
            out["per_ticker"].append({"ticker": sym, "error": str(ex)[:200]})
            continue
        pol = res.policy
        row = {"ticker": sym, "classification": pol.classification,
               "p_success": round(pol.p_success, 4), "ev_r": round(pol.ev_r, 3),
               "size_pct": round(pol.size_pct, 2),
               "setup": res.structure.active_setup if res.structure else None,
               "regime": pol.regime_flag,
               "actions": pol.actions[:6]}
        out["per_ticker"].append(row)
        ps.append(pol.p_success)
        evs.append(pol.ev_r)
        cls = pol.classification.upper()
        if "ACTIONABLE" in cls:
            out["actionable"] += 1
            actionables.append(row)
        elif "WATCH" in cls:
            out["watchlist"] += 1
        elif "RESERVE" in cls:
            out["reserve"] += 1
        else:
            out["rejected"] += 1
        emit(f"    -> {sym:<6} {pol.classification:<12} p={pol.p_success:.3f} "
             f"EV={pol.ev_r:+.2f}R size={pol.size_pct:.1f}% setup={row['setup']}")

    if source in ("yahoo-live", "cache(real_data_cache.json)"):
        agg_g, agg_f = [], []
        for sym, cs in dfs.items():
            st = empirical_limit_stats(cs)
            agg_g.append(st["gap_down_freq"])
            agg_f.append(st["floor_freq"])
        out["empirical"] = {"gap_down_freq": round(sum(agg_g) / len(agg_g), 4),
                            "floor_freq": round(sum(agg_f) / len(agg_f), 4)}
        prior_gap, prior_floor = 0.08, 0.02
        emit(f"  EMPIRICAL gap-down={out['empirical']['gap_down_freq']:.3f} "
             f"(MC prior {prior_gap}), floor={out['empirical']['floor_freq']:.4f} "
             f"(MC prior {prior_floor})")
        if abs(out["empirical"]["gap_down_freq"] - prior_gap) > 0.03:
            emit("  [ISSUE] prior gap-down lech >0.03 khoi thuc te -> p99 MC sai he so")

    n_neg_ev_actionable = sum(1 for r in actionables if r["ev_r"] < 0)
    if ps:
        out["p_dist"] = {"min": min(ps), "max": max(ps),
                         "mean": round(sum(ps) / len(ps), 4)}
        out["ev_dist"] = {"min": min(evs), "max": max(evs)}
    emit(f"  COVERAGE ACTIONABLE: {out['actionable']}/{out['loaded']} "
         f"| WATCHLIST {out['watchlist']} | RESERVE {out['reserve']} | REJECT {out['rejected']}")
    emit(f"  p_dist={out.get('p_dist')} ev_dist={out.get('ev_dist')}")
    if n_neg_ev_actionable:
        emit(f"  [FAIL] {n_neg_ev_actionable} ACTIONABLE co EV<0 -> gate EV chua duoc enforce")
    out["n_actionable_negative_ev"] = n_neg_ev_actionable
    record("s5_real_pipeline", out)


# ----------------------------------------------------------------------
# [7] S6 walk-forward
# ----------------------------------------------------------------------
def check_walkforward() -> None:
    section("[7/8] S6 — WALK-FORWARD SPLIT INTEGRITY")
    try:
        from wfe.backtest.walk_forward import WalkForwardValidator
        vw = WalkForwardValidator(k_folds=5, embargo_bars=5)
        splits = vw.split(1000)
        emit(f"    n_splits actual = {len(splits)} (request 5)")
        gaps = []
        for tr, te in splits:
            emit(f"      train={tuple(tr)} test={tuple(te)} gap={te[0]-tr[1]}")
            gaps.append(te[0] - tr[1])
        emb_ok = bool(gaps) and min(gaps) >= 5
        emit(f"  [ {'OK' if emb_ok else 'FAIL'} ] gap >= embargo: {gaps}")
        emit("  [WARN] embargo 5 bars << holding period tranche-ladder (vài tuần) "
             "-> leakage label tiem an khi backtest that")
        record("s6_walkforward", {"n_splits": len(splits), "gaps": gaps,
                                  "embargo_respected": emb_ok})
    except Exception as ex:
        emit(f"  [ERROR] {type(ex).__name__}: {ex}")
        record("s6_walkforward", {"error": str(ex)[:300]})


# ----------------------------------------------------------------------
# [8] legacy bridge
# ----------------------------------------------------------------------
def check_legacy_bridge() -> None:
    section("[8/8] LEGACY BRIDGE — vnstock_server import + classify smoke")
    out = {"import_ok": False, "error": None}
    try:
        # Tai file truc tiep (giong tests/) vi ten package 'mcp' xung dot voi
        # PyPI `mcp` da cai san.
        import importlib.util
        server_path = REPO_ROOT / "mcp" / "vnstock_server.py"
        spec = importlib.util.spec_from_file_location("vnstock_server", str(server_path))
        vs = importlib.util.module_from_spec(spec)
        sys.modules.setdefault("vnstock_server", vs)
        spec.loader.exec_module(vs)
        out["import_ok"] = True
        fn = getattr(vs, "classify_vpa", None)
        if fn:
            n = 40
            c = [100 + i * 0.5 for i in range(n)]
            o = [x - 0.2 for x in c]
            h = [x + 0.6 for x in c]
            l = [x - 0.6 for x in c]
            v = [1000 + (i % 5) * 100 for i in range(n)]
            sma = sum(v[-20:]) / 20
            out["classify_smoke"] = str(fn(c, o, h, l, v, n - 1, sma))[:120]
            emit(f"  [ OK ] import OK; classify_vpa smoke: {out['classify_smoke']}")
        else:
            emit("  [ OK ] import OK (khong tim thay classify_vpa de smoke)")
    except Exception as ex:
        out["error"] = f"{type(ex).__name__}: {str(ex)[:300]}"
        emit(f"  [FAIL] {out['error']}")
    record("legacy_bridge", out)


# ----------------------------------------------------------------------
# Summary + writers
# ----------------------------------------------------------------------
def final_summary() -> None:
    section("TONG HOP DIAGNOSTIC")
    c = RESULTS_JSON["checks"]
    t = c.get("tests", {})
    s1, s2 = c.get("s1_determinism", {}), c.get("s2_calibration", {})
    s3, s4 = c.get("s3_killswitch", {}), c.get("s4_hysteresis", {})
    s5 = c.get("s5_real_pipeline", {})
    checks = [
        ("Unit tests 0 failed/0 error", bool(t.get("ran")) and not t.get("failed") and not t.get("errors")),
        ("MC deterministic (in-proc & cross-proc)", s1.get("in_process_reproducible") and s1.get("cross_process_reproducible")),
        ("EV(0.5) anchored ~0", s2.get("anchor_ok")),
        ("Kill-switch down_rank effective", s3.get("effective")),
        ("Regime hysteresis suppresses flip-flop", s4.get("pass")),
        ("Real-data pipeline ran", s5.get("loaded", 0) > 0),
        ("No ACTIONABLE with EV<0", s5.get("loaded", 0) > 0 and s5.get("n_actionable_negative_ev", 0) == 0),
    ]
    for name, cond in checks:
        emit(f"  [{'PASS' if cond else 'ISSUE'}] {name}")
    emit(f"  Coverage ACTIONABLE tren nguon '{s5.get('source')}': "
         f"{s5.get('actionable', '?')}/{s5.get('loaded', '?')} tickers")
    emit("")
    emit("  => GUI 2 FILE SAU CHO AI PHAN TICH:")
    emit(f"     1. {REPORT_PATH.name}")
    emit(f"     2. {JSON_PATH.name}")
    if s5.get("source") in (None, "offline-synthetic"):
        emit("  !! Luu y: S5 CHUA chay tren du lieu that — chay lai khong --no-network")


def write_reports() -> None:
    REPORT_PATH.write_text("\n".join(REPORT_LINES), encoding="utf-8")
    JSON_PATH.write_text(json.dumps(RESULTS_JSON, indent=2, ensure_ascii=False,
                                    default=str), encoding="utf-8")
    print(f"\nSaved: {REPORT_PATH}\nSaved: {JSON_PATH}")


def main() -> int:
    ap = argparse.ArgumentParser(description="WFE V3.5 diagnostic report")
    ap.add_argument("--no-network", action="store_true",
                    help="bo qua download du lieu that (dung cache/offline neu co)")
    ap.add_argument("--universe-size", type=int, default=28)
    ap.add_argument("--days", type=int, default=730, help="lich su ngay: 365/730/1095/1825")
    ap.add_argument("--offline-universe", action="store_true",
                    help="ep dung wfe/ops/offline_universe.json thay vi du lieu that")
    args = ap.parse_args()

    RESULTS_JSON["meta"] = {"argv": sys.argv, "ts": datetime.now(timezone.utc).isoformat(),
                            "universe_size": args.universe_size, "days": args.days}

    if not check_environment():
        emit("\nTHIEU TIEN QUYET — fix theo huong dan tren roi chay lai.")
        emit("Windows cmd:  py -3 -m pip install numpy pandas scipy pytest")
        write_reports()
        return 2

    try:
        run_test_suite()
    except Exception as ex:
        emit(f"  [ERROR] test suite crash: {ex}")
    for fn in (check_determinism, check_calibration, check_killswitch,
               check_hysteresis, check_walkforward, check_legacy_bridge):
        try:
            fn()
        except Exception:
            emit(f"  [ERROR] {fn.__name__}:")
            emit(traceback.format_exc()[-1200:])
    try:
        check_pipeline_real_data(min(args.universe_size, len(UNIVERSE_LARGE) + len(UNIVERSE_SMALL)),
                                 args.days, not args.no_network, args.offline_universe)
    except Exception:
        emit("  [ERROR] pipeline real-data:")
        emit(traceback.format_exc()[-2000:])
    final_summary()
    write_reports()
    return 0


if __name__ == "__main__":
    sys.exit(main())
