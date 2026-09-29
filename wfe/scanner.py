"""
WFE Orchestrator & Scanner V3.0
Pipeline: L0 Data -> L1 Three Engines -> L2 Policy -> L3 Risk -> L4 Ops -> L5 Output
"""

import os
import json
from typing import List, Dict, Any, Optional
from wfe.config.registry import DEFAULT_REGISTRY, WFERegistry
from wfe.data.pit_feed import PITFeed, BarSeries, MarketBar
from wfe.engines.flow_engine import FlowEngine, FlowOutput
from wfe.engines.structure_engine import StructureEngine, StructureOutput
from wfe.engines.volume_engine import VolumeEngine, VolumeOutput
from wfe.policy.policy_engine import PolicyEngine, PolicyDecision
from wfe.risk.state_machine import calculate_sl1, compute_atr14, simulate_gap_floor_risk
from wfe.ops.governance import KillSwitchManager, DriftMonitor
from wfe.output.schema import assemble_wfe_output, WFESchemaOutput


class WFEScanner:
    """Master scanner running WFE V3.0 pipeline."""

    def __init__(self, registry: Optional[WFERegistry] = None):
        self.registry = registry or DEFAULT_REGISTRY
        self.pit_feed = PITFeed(
            min_bars=self.registry.ops.min_history_bars,
            min_adtv_bil=self.registry.ops.min_adtv_bil
        )
        self.flow_engine = FlowEngine(self.registry.flow)
        self.structure_engine = StructureEngine(self.registry.structure)
        self.volume_engine = VolumeEngine(self.registry.volume)
        self.policy_engine = PolicyEngine(self.registry.policy)
        self.kill_switch = KillSwitchManager(self.registry.ops.flow_mode)
        self.drift_monitor = DriftMonitor(
            window_size=self.registry.ops.drift_window_bars,
            z_threshold=self.registry.ops.drift_z_threshold
        )

    def analyze_symbol(
        self,
        symbol: str,
        raw_candles: List[Dict[str, Any]],
        exchange: str = "HOSE",
        sector: str = "Chung",
        pit_status: str = "NORMAL"
    ) -> WFESchemaOutput:
        """Runs the entire L0-L5 pipeline on a single stock."""

        # 1. L0: Point-In-Time Validation & Quality Check
        series = self.pit_feed.process_raw_candles(
            symbol=symbol,
            raw_candles=raw_candles,
            exchange=exchange,
            sector=sector,
            pit_status=pit_status
        )

        if not series.data_ok or len(series.bars) < self.registry.ops.min_history_bars:
            # Emit data_ok=False schema with empty structures
            empty_flow = self.flow_engine.calculate([])
            empty_struct = self.structure_engine.calculate([])
            empty_vol = self.volume_engine.calculate([])
            empty_policy = self.policy_engine.evaluate([], empty_flow, empty_struct, empty_vol)
            empty_policy.trace.append(f"L0 Rejected: {series.rejection_reason or 'Insufficient data'}")

            return assemble_wfe_output(
                symbol=symbol,
                date=raw_candles[-1].get("date", "N/A") if raw_candles else "N/A",
                current_price=0.0,
                flow=empty_flow,
                structure=empty_struct,
                volume=empty_vol,
                policy=empty_policy
            )

        bars = series.bars
        curr_price = bars[-1].close
        curr_date = bars[-1].date

        # 2. L1: Structure Engine (Trading Range, Events, Stationarity, Levels, Phases)
        structure_res = self.structure_engine.calculate(bars)

        # 3. L1: Volume Engine (Candle quality & Event evaluation)
        events_dicts = [
            {"event_id": ev.event_id, "event_type": ev.event_type, "bar_index": ev.bar_index}
            for ev in structure_res.events
        ]
        volume_res = self.volume_engine.calculate(bars, events_to_evaluate=events_dicts)

        # 4. L1: Flow Engine (Trend, Accumulation, Distribution)
        # Pass breakout state and any test depletion quality via policy interface
        is_breakout = curr_price > structure_res.levels.tr_high
        flow_res = self.flow_engine.calculate(
            bars,
            is_breakout=is_breakout,
            pivot_reference=structure_res.levels.tr_high
        )

        # 5. L2: Policy Engine (Expectancy EV decision & Tranche Ladder)
        policy_res = self.policy_engine.evaluate(
            bars=bars,
            flow=flow_res,
            structure=structure_res,
            volume=volume_res,
            kill_switch_flow_off=self.kill_switch.is_flow_off
        )

        # 6. L3: Risk & Gap/Floor Simulation
        atr14 = compute_atr14(bars)
        # Q2 Single Source of Truth for Stops:
        # sl1 is taken directly from the operative tranche of the active setup
        if structure_res.active_setup == "TEST_SPRING_PHASE_C" and policy_res.tranche_plans:
            sl1 = policy_res.tranche_plans[0].stop_loss
        elif structure_res.active_setup == "BU_LPS_PHASE_D" and len(policy_res.tranche_plans) > 1:
            sl1 = policy_res.tranche_plans[1].stop_loss
        elif policy_res.tranche_plans:
            sl1 = policy_res.tranche_plans[0].stop_loss
        else:
            sl1 = calculate_sl1(bars, atr14=atr14, atr_mult=self.registry.risk.sl1_atr_mult)

        # Patch V3.1: 3.w Stop sanity band
        stop_dist = (curr_price - sl1) / curr_price if curr_price > 0 else 0.0
        max_stop_band = max(2.5 * atr14 / curr_price, 0.10) if curr_price > 0 else 0.10
        if stop_dist > max_stop_band:
            policy_res.actions.append(f"flag: [STOP_WIDE] (stop_dist={stop_dist*100:.1f}% > {max_stop_band*100:.1f}%)")
            for tp in policy_res.tranche_plans:
                if tp.tranche_id == "T0_PROBE":
                    tp.is_eligible = False

        raw_size = policy_res.final_size_pct
        p99_capped_size = raw_size
        port_capped_size = raw_size
        liq_capped_size = raw_size

        if policy_res.classification == "ACTIONABLE" and policy_res.final_size_pct > 0:
            # Patch V3.1: 3.z Risk cap là ràng buộc cứng
            p99_loss_nav = simulate_gap_floor_risk(
                entry_price=curr_price,
                sl=sl1,
                nav_allocation_pct=policy_res.final_size_pct / 100.0,
                num_simulations=2000
            )
            max_risk = self.registry.risk.max_total_risk_p99_nav
            if p99_loss_nav > max_risk:
                old_size = policy_res.final_size_pct
                scale = max_risk / p99_loss_nav
                policy_res.final_size_pct = max(0.0, round(policy_res.final_size_pct * scale, 1))
                policy_res.actions.append(f"downsize: p99 risk {p99_loss_nav*100:.2f}% > {max_risk*100:.1f}% -> size {old_size}% down to {policy_res.final_size_pct}%")
            p99_capped_size = policy_res.final_size_pct

            # Patch V3.2 P1: Single-stock concentration cap (max 25% NAV per stock)
            max_stock_pct = self.registry.policy.max_nav_per_stock * 100.0
            if policy_res.final_size_pct > max_stock_pct:
                old_size = policy_res.final_size_pct
                policy_res.final_size_pct = round(max_stock_pct, 1)
                port_capped_size = policy_res.final_size_pct
                policy_res.actions.append(f"downsize: portfolio_cap (max {max_stock_pct:.0f}% NAV/mã, {old_size}% -> {policy_res.final_size_pct}%)")

            # Patch V3.3 Q4: Output Liquidity Exit Cap (size_i * reference_nav <= max_adtv_exit_ratio * ADTV20_i)
            ref_nav = getattr(self.registry.policy, "reference_nav_bil", 15.0)
            max_ratio = getattr(self.registry.policy, "max_adtv_exit_ratio", 0.20)
            if series.adtv20_bil and series.adtv20_bil > 0 and ref_nav > 0:
                max_liq_pct = round((max_ratio * series.adtv20_bil / ref_nav) * 100.0, 1)
                if policy_res.final_size_pct > max_liq_pct:
                    old_size = policy_res.final_size_pct
                    policy_res.final_size_pct = max_liq_pct
                    liq_capped_size = policy_res.final_size_pct
                    policy_res.actions.append(f"downsize: liquidity_cap (ADTV20={series.adtv20_bil:.2f}B, max {max_ratio*100:.0f}% exit={max_liq_pct:.1f}% NAV, {old_size}% -> {policy_res.final_size_pct}%)")
                else:
                    liq_capped_size = policy_res.final_size_pct
            else:
                liq_capped_size = policy_res.final_size_pct

            # Recalculate p99 loss for final capped size
            p99_loss_nav = simulate_gap_floor_risk(
                entry_price=curr_price,
                sl=sl1,
                nav_allocation_pct=policy_res.final_size_pct / 100.0,
                num_simulations=2000
            )

            if policy_res.final_size_pct < 5.0:
                policy_res.final_size_pct = 0.0
                policy_res.classification = "WATCHLIST"
                policy_res.actions.append("exclude: size < 5% NAV after risk haircut -> moved to WATCHLIST")
        else:
            p99_loss_nav = 0.0

        # Patch V3.3: Cap loop audit trace
        policy_res.trace.append(
            f"Cap Loop Audit: raw_size={raw_size:.1f}% -> p99_capped={p99_capped_size:.1f}% -> "
            f"portfolio_capped={port_capped_size:.1f}% -> liquidity_capped={liq_capped_size:.1f}% -> final_size={policy_res.final_size_pct:.1f}%"
        )

        policy_res.trace.append(
            f"Risk Check: Entry={curr_price:.2f}, SL1={sl1:.2f}, ATR14={atr14:.2f}, "
            f"p99_simulated_loss_nav={p99_loss_nav*100:.2f}% (Limit <= {self.registry.risk.max_total_risk_p99_nav*100:.1f}%)"
        )

        # 7. L4: Ops & Drift Monitoring
        if flow_res.data_ok and flow_res.trend.value is not None:
            self.drift_monitor.record_observation("flow_trend", flow_res.trend.value)
            self.drift_monitor.record_observation("flow_accum", flow_res.accum.value)
            self.drift_monitor.record_observation("flow_dist", flow_res.dist.value)

        # 8. L5: Output Assembly
        output_schema = assemble_wfe_output(
            symbol=symbol,
            date=curr_date,
            current_price=curr_price,
            flow=flow_res,
            structure=structure_res,
            volume=volume_res,
            policy=policy_res
        )

        return output_schema

    def scan_universe(
        self,
        candles_by_symbol: Dict[str, List[Dict[str, Any]]],
        top_n: int = 10,
        min_p_success: float = 0.45,
        min_avg_val_bil: float = 15.0
    ) -> Dict[str, Any]:
        """Scans multiple stocks and returns qualified ranked candidates."""
        results = []
        rejected = 0
        all_results_by_sym = {}

        for sym, candles in candles_by_symbol.items():
            res = self.analyze_symbol(sym, candles)
            all_results_by_sym[sym] = res
            if not res.policy or not res.policy.data_ok:
                rejected += 1
                continue

            # Filter candidates by minimum p_success
            if res.policy.p_success >= min_p_success:
                results.append(res)

        # Patch V3.2 & V3.5: Portfolio budget constraint (sum of approved_size <= nav_budget)
        actionable_candidates = [c for c in results if c.classification == "ACTIONABLE"]
        total_approved = sum(c.policy.size_pct for c in actionable_candidates)
        budget_pct = self.registry.policy.nav_budget * 100.0
        if total_approved > budget_pct:
            # Sort by EV ascending to downsize lower EV candidates first
            actionable_candidates.sort(key=lambda x: x.policy.ev_r)
            excess = total_approved - budget_pct
            for c in actionable_candidates:
                if excess <= 0:
                    break
                curr_s = c.policy.size_pct
                reduction = min(curr_s, excess)
                new_s = round(curr_s - reduction, 1)
                excess -= reduction
                c.policy.size_pct = new_s
                if new_s <= 0.0:
                    c.classification = "RESERVE"
                    c.policy.classification = "RESERVE"
                    c.actions.append(f"downsize: portfolio_budget_cap ({curr_s}% -> 0.0%) -> moved to RESERVE (hết hạn mức danh mục {budget_pct:.0f}% NAV)")
                    c.trace.append(f"Portfolio Budget Cap: reduced from {curr_s}% to 0.0% -> Reclassified as RESERVE")
                else:
                    c.actions.append(f"downsize: portfolio_budget_cap ({curr_s}% -> {new_s}%)")
                    c.trace.append(f"Portfolio Budget Cap: reduced from {curr_s}% to {new_s}% (total budget {budget_pct}%)")

        # Sort by p_success and ev_r descending
        results.sort(key=lambda x: (x.policy.p_success, x.policy.ev_r), reverse=True)

        top_candidates = results[:top_n]

        # Patch V3.5 R5: Diff-based Drop-out Manifest
        state_file = os.path.join(os.path.dirname(__file__), "ops", "last_run_state.json")
        prev_state = {}
        if os.path.exists(state_file):
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    prev_state = json.load(f)
            except Exception:
                prev_state = {}

        current_active_syms = set([c.symbol for c in top_candidates])
        drop_out_manifest = []

        if prev_state and "candidates" in prev_state:
            prev_candidates = prev_state["candidates"]
            top_cut_off = top_candidates[-1].policy.p_success if len(top_candidates) >= top_n else min_p_success
            for prev_c in prev_candidates:
                sym = prev_c.get("symbol")
                if not sym or sym in current_active_syms:
                    continue
                prev_status = prev_c.get("classification", "N/A")
                if sym not in all_results_by_sym:
                    reason = "Dữ liệu không đủ hoặc bị loại bởi bộ lọc PIT"
                    cat = "DROPPED_DATA"
                else:
                    cur_res = all_results_by_sym[sym]
                    cur_p = cur_res.policy.p_success if cur_res.policy else 0.0
                    cur_cls = cur_res.classification
                    if cur_p < min_p_success:
                        reason = f"Điểm p_success ({cur_p*100:.1f}%) < ngưỡng tối thiểu {min_p_success*100:.0f}%"
                        cat = "DROPPED_SCORE"
                    elif cur_cls == "WATCHLIST" and prev_status == "ACTIONABLE":
                        reason = f"Chuyển từ ACTIONABLE sang WATCHLIST: {', '.join(cur_res.actions[:2]) or 'chưa kích hoạt setup'}"
                        cat = "STATUS_DOWNGRADE"
                    elif cur_p >= min_p_success:
                        reason = f"Rớt hạng ngoài Top {top_n} do các mã khác có điểm ưu tiên cao hơn ({cur_p*100:.1f}% < cut-off {top_cut_off*100:.1f}%)"
                        cat = "RANK_DROPOUT"
                    else:
                        reason = "Vi phạm ngưỡng cắt lỗ hoặc phá vỡ cấu trúc hộp"
                        cat = "STRUCTURE_BREAK"

                drop_out_manifest.append({
                    "symbol": sym,
                    "prev_status": prev_status,
                    "reason": reason,
                    "category": cat
                })

        # Persist current candidates for subsequent run diff
        current_state = {
            "date": top_candidates[0].date if top_candidates else "N/A",
            "candidates": [
                {"symbol": c.symbol, "classification": c.classification, "p_success": c.policy.p_success}
                for c in results[:max(top_n, 15)]
            ]
        }
        try:
            os.makedirs(os.path.dirname(state_file), exist_ok=True)
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(current_state, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        return {
            "total_scanned": len(candles_by_symbol),
            "qualified_count": len(results),
            "rejected_data_quality": rejected,
            "top_candidates": [c.to_dict() for c in top_candidates],
            "drop_out_manifest": drop_out_manifest,
            "global_params_hash": self.registry.global_hash,
            "system_version": self.registry.version
        }
