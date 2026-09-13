"""One Q4 execution bundle; bounded P1 by default, annual only when selected."""
import argparse
import inspect
import importlib.metadata
import json
import platform
import sys
import subprocess
from time import perf_counter
from pathlib import Path

import numpy as np
import pandas as pd

from q4_core import ROOT, VERSION, MidnightPolicy, model, online, interval_ledger, summarize, validate_ledger
from q4_prices import forecast_prices, load_prices
from q4_provenance import verify_q2, upstream_path, source_snapshot, input_snapshot, sha256, write_json
from q4_delivery import write_template, tables_and_figures


def q42(data, load_pred, pv_pred, prices, end_day):
    policy = MidnightPolicy(data, load_pred, pv_pred)
    planned, executed = 6000., 6000.
    frames, decisions = [], []
    for day in range(end_day+1):
        forecast = forecast_prices(data.dates, prices, data.price, day, data.dates[day])
        selected, plans, diagnostics = policy.plan(day, planned, forecast)
        grid = plans[selected]
        settled = model.settle_causally(grid, data.load[day], data.pv[day], executed)
        frames.append(interval_ledger(data, day, grid, grid, settled, forecast, planned, executed, prices[day], selected))
        frames[-1]["load_forecast_kw"] = load_pred[day]
        frames[-1]["pv_forecast_kw"] = pv_pred[day]
        policy.settle_candidate_scores(day, plans, executed, prices[day])
        decisions.append({"day_index": day, "selected_candidate": selected,
                          "planned_initial_energy_kwh": planned, "executed_initial_energy_kwh": executed,
                          "latest_full_score_day_released": day-2, "diagnostics": json.dumps(diagnostics)})
        planned = online.project_pending_energy(settled["soc"][-2], grid[-1], load_pred[day,-1], pv_pred[day,-1])
        executed = float(settled["soc"][-1])
        print(f"Q4-2 {day+1}/{end_day+1} {selected}", flush=True)
    return pd.concat(frames, ignore_index=True), pd.DataFrame(decisions)


def q43(data, load_pred, pv_pred, prices, end_day, settlement, adjustment_start_day):
    sys.path.insert(0, str(ROOT / "solutions/Q3_V3_ALIGNED/program"))
    import q3_api
    if "on_day_complete" not in inspect.signature(q3_api.simulate).parameters:
        raise RuntimeError("Q3 simulate requires on_day_complete(day, executed_initial_soc) for real ONLINE-RISK-SP scoring")
    inputs = q3_api.load_inputs()
    upstream = q3_api.load_upstream(run_path=upstream_path())
    policy = MidnightPolicy(data, load_pred, pv_pred)
    pending, records = {}, {}
    price_rows = []

    def midnight(day, predicted_initial_soc):
        f = forecast_prices(data.dates, prices, data.price, day, data.dates[day])
        selected, plans, diagnostics = policy.plan(day, predicted_initial_soc, f)
        pending[day] = plans
        records[day] = (f, selected, diagnostics)
        return plans[selected].copy()

    def completed(day, executed_initial_soc):
        policy.settle_candidate_scores(day, pending.pop(day), executed_initial_soc, prices[day])

    def decision_price(day, hour, steps):
        f = forecast_prices(data.dates, prices, data.price, day, data.dates[day]+pd.Timedelta(hours=hour))
        for step in steps:
            price_rows.append({"day_index": day, "release_hour": hour, "time_index": int(step),
                "issue_time": f.issue_time, "source_completed_at": f.source_completed_at[step],
                "price_forecast_yuan_per_kwh": f.values[step], "price_model_id": f.model_id})
        return f.values[steps].copy()

    raw, adjustments, daily = q3_api.simulate(inputs, upstream, end_day=end_day,
        adjustment_start_day=adjustment_start_day, settlement=settlement,
        decision_price=decision_price, settlement_price=prices, q0_override=midnight,
        on_day_complete=completed)
    frames = []
    for day in range(end_day+1):
        rows = raw[raw.day_index == day].sort_values("time_index")
        meta = daily[daily.day_index == day].iloc[0]
        f, selected, diagnostics = records[day]
        settled = {"c": rows.charge_kwh.to_numpy(), "d": rows.discharge_kwh.to_numpy(),
            "emergency": rows.emergency_kwh.to_numpy(), "spill": rows.unused_supply_kwh.to_numpy(),
            "soc": np.r_[rows.soc_before_kwh.iloc[0], rows.soc_after_kwh.to_numpy()]}
        frame = interval_ledger(data, day, rows.q0_kwh.to_numpy(), rows.qfinal_kwh.to_numpy(),
            settled, f, meta.planned_initial_energy_kwh, meta.executed_initial_energy_kwh, prices[day], selected, settlement)
        frame["confirmation_count"] = rows.confirmation_count.to_numpy()
        frame["load_forecast_kw"] = load_pred[day]
        frame["pv_forecast_kw"] = pv_pred[day]
        frame["release_used"] = rows.release_used.to_numpy()
        if frame.confirmation_count.max() > 1:
            raise AssertionError("duplicate Q3 confirmation")
        if not np.allclose(frame.final_grid_kwh.iloc[:35], frame.planned_grid_kwh.iloc[:35]):
            raise AssertionError("Q3 changed locked early contract")
        for ours, theirs in (("cash_cost_yuan", "total_cost_yuan"), ("ordinary_cost_yuan", "ordinary_cost_yuan")):
            if not np.allclose(frame[ours], rows[theirs], atol=1e-6, rtol=0):
                raise AssertionError("Q3/Q4 independent settlement mismatch")
        frames.append(frame)
        records[day] = {"day_index": day, "selected_candidate": selected, "diagnostics": json.dumps(diagnostics)}
    return pd.concat(frames, ignore_index=True), adjustments, pd.DataFrame(records.values()), pd.DataFrame(price_rows), daily


def run(args):
    if not args.run_id or Path(args.run_id).name != args.run_id:
        raise ValueError("run-id must be a single path component")
    end_day = 364 if args.mode == "annual" else args.p1_days-1
    if args.mode == "p1" and not 2 <= args.p1_days <= 7:
        raise ValueError("P1 is bounded to 2-7 real consecutive days")
    root = VERSION / "results" / args.run_id
    root.mkdir(parents=True, exist_ok=False)
    figures = VERSION / "figures" / args.run_id
    figures.mkdir(parents=True, exist_ok=False)
    started = perf_counter()
    manifest = {"status": "running", "formal_use": False, "review_status": "NOT_REVIEWED",
        "mode": args.mode, "command": sys.argv, "python": sys.version, "platform": platform.platform(),
        "source_hashes": source_snapshot(), "input_hashes": input_snapshot(),
        "policy": "ONLINE-RISK-SP-A-S10-BATA-OBS0-RESET0/B0/PRICE-LAG7",
        "settlement": "A primary; B independent policy sensitivity", "annual_reproduction": False}
    manifest["source_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    manifest["packages"] = {name: importlib.metadata.version(name) for name in ("numpy", "pandas", "scipy", "openpyxl", "matplotlib", "scikit-learn")}
    manifest["p1_adjustment_start_day"] = 0 if args.mode == "p1" else 31
    write_json(root / "manifest.json", manifest)
    try:
        manifest["upstream"] = verify_q2()
        data = model.load_data()
        with np.load(upstream_path() / "forecast_bundle.npz", allow_pickle=False) as bundle:
            load_pred, pv_pred = bundle["load_b0"].copy(), bundle["pv_b0"].copy()
        prices = load_prices(ROOT / "data/附件4.xlsx", data.dates)
        summary = {}
        ledger42, decisions42 = q42(data, load_pred, pv_pred, prices, end_day)
        outputs = [("q4_2", 2, ledger42)]
        decisions42.to_csv(root / "q4_2_candidates.csv", index=False)
        # P1 exercises real releases from day zero, labelled nonannual diagnostics.
        for settlement in ("A", "B"):
            prefix = f"q4_3_{settlement}"
            frame, changes, candidates, price_log, daily = q43(data, load_pred, pv_pred, prices,
                end_day, settlement, 31 if args.mode == "annual" else 0)
            outputs.append((prefix, 3, frame))
            changes.to_csv(root / f"{prefix}_adjustments.csv", index=False)
            candidates.to_csv(root / f"{prefix}_candidates.csv", index=False)
            price_log.to_csv(root / f"{prefix}_price_forecasts.csv", index=False)
            daily.to_csv(root / f"{prefix}_plans.csv", index=False)
        for prefix, part, full in outputs:
            validate_ledger(full)
            full.to_csv(root / f"{prefix}_all_intervals.csv", index=False)
            report = full[full.plan_day >= "2025-02-01"].copy() if args.mode == "annual" else full
            report.to_csv(root / f"{prefix}_interval_ledger.csv", index=False)
            summary[prefix] = summarize(report)
            filename = "result4-2.xlsx" if part == 2 else ("result4-3.xlsx" if prefix.endswith("_A") else "result4-3-B-sensitivity.xlsx")
            summary[prefix]["template_readback"] = write_template(report, root / filename, part, args.mode == "annual", full)
            tables_and_figures(report, root, figures, prefix, full)
        comparison = pd.DataFrame({name: frame.groupby("plan_day").cash_cost_yuan.sum() for name, _, frame in outputs})
        comparison["A_minus_q42_yuan"] = comparison.q4_3_A - comparison.q4_2
        comparison["B_minus_A_yuan"] = comparison.q4_3_B - comparison.q4_3_A
        comparison.to_csv(root / "paired_daily_comparison.csv")
        write_json(root / "summary.json", summary)
        manifest["status"] = "complete_provisional"
        manifest["summary"] = summary
    except BaseException as exc:
        manifest["status"], manifest["error"] = "failed", repr(exc)
        raise
    finally:
        manifest["elapsed_seconds"] = perf_counter()-started
        manifest["source_hashes_after"] = source_snapshot()
        manifest["sources_unchanged"] = manifest["source_hashes"] == manifest["source_hashes_after"]
        if not manifest["sources_unchanged"]:
            manifest["status"] = "failed_source_changed"
        manifest["outputs"] = {str(p.relative_to(VERSION)): sha256(p) for base in (root, figures)
            for p in sorted(base.rglob("*")) if p.is_file() and p.name != "manifest.json"}
        write_json(root / "manifest.json", manifest)
    if not manifest["sources_unchanged"]:
        raise RuntimeError("source changed during execution; review before using artifacts")
    return root


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("p1", "annual"), default="p1")
    p.add_argument("--run-id", required=True)
    p.add_argument("--p1-days", type=int, default=3)
    return p


if __name__ == "__main__":
    print(run(parser().parse_args()))
