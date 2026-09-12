"""Strictly causal online selector for Q2 risk/scenario parameters.

At each day, all candidate configurations are solved from the same real SOC
using only information available before the day.  Their costs become available
to the selector only after today's actual settlement, so tomorrow's choice can
use them without leaking today's outcome into today's decision.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd

from q2_model import (
    DT,
    E_INIT,
    K_EMERGENCY,
    TEST_DAYS,
    build_forecasts,
    load_data,
    plan_battery_for_fixed_grid,
    save_policy_npz,
    settle_causally,
    settle_planned_battery,
    summarize_policy,
    two_stage_plan,
)
from run_q2_advanced_search import recency_factory
from q2_validation_v3 import shift_right_endpoint_to_left_slots


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "Q2/results/q2_final_validation_v3/07_online_selector"
RUNS = OUT / "runs"
WINDOW_DAYS = 28
SCENARIO_COUNT = 10
SCENARIO_WINDOW = 60
TERMINAL_LAMBDA = 0.4684
_WORKER: dict = {}
TIME_MAPPING = "A"


def candidate_grid() -> list[dict]:
    rows = []
    for gamma in (0.0, 0.02, 0.05):
        rows.append({
            "candidate_id": f"nocvar_g{gamma:.2f}",
            "tau": None, "rho": 0.0, "gamma": gamma,
        })
        for tau in (0.90, 0.95):
            for rho in (0.05, 0.20):
                rows.append({
                    "candidate_id": f"cvar_t{tau:.2f}_r{rho:.2f}_g{gamma:.2f}",
                    "tau": tau, "rho": rho, "gamma": gamma,
                })
    return rows


def _shifted_data():
    original = load_data()
    return replace(
        original,
        price=shift_right_endpoint_to_left_slots(original.price),
        load=shift_right_endpoint_to_left_slots(original.load),
        pv=shift_right_endpoint_to_left_slots(original.pv),
    )


def _worker_init(time_mapping: str) -> None:
    data = load_data() if time_mapping == "A" else _shifted_data()
    load_fc, pv_fc = build_forecasts(data)
    _WORKER["data"] = data
    _WORKER["load_pred"] = load_fc["same_weekday_2w"]
    _WORKER["pv_pred"] = pv_fc["recent_5d"]
    _WORKER["scenario_cache"] = {}


def _solve_candidate(
    task: tuple[int, float, dict, int, str],
) -> tuple[str, dict]:
    day, e0, candidate, scenario_count, battery_interpretation = task
    data = _WORKER["data"]
    load_pred = _WORKER["load_pred"]
    pv_pred = _WORKER["pv_pred"]
    cache = _WORKER["scenario_cache"]
    key = (int(day), float(candidate["gamma"]), int(scenario_count))
    if key not in cache:
        cache[key] = recency_factory(candidate["gamma"])(
            data, load_pred, pv_pred, int(day),
            count=int(scenario_count), window=SCENARIO_WINDOW,
        )
        if len(cache) > 128:
            cache.clear()
            cache[key] = recency_factory(candidate["gamma"])(
                data, load_pred, pv_pred, int(day),
                count=int(scenario_count), window=SCENARIO_WINDOW,
            )
    load_sc, pv_sc, weights = cache[key]
    g, diag = two_stage_plan(
        data.price, load_sc, pv_sc, weights, e0,
        terminal="value", terminal_lambda=TERMINAL_LAMBDA,
        cvar_beta=candidate["tau"] or 0.0,
        cvar_weight=candidate["rho"],
    )
    if battery_interpretation == "A":
        settled = settle_causally(g, data.load[day], data.pv[day], e0)
    elif battery_interpretation == "B":
        expected_load = np.average(load_sc, axis=0, weights=weights)
        expected_pv = np.average(pv_sc, axis=0, weights=weights)
        _, _, battery_plan = two_stage_plan(
            data.price, expected_load[None, :], expected_pv[None, :],
            np.array([1.0]), e0,
            terminal="value", terminal_lambda=TERMINAL_LAMBDA,
            fixed_g=g, return_full_plan=True,
        )
        settled = settle_planned_battery(
            g, battery_plan["c"], battery_plan["d"],
            data.load[day], data.pv[day], e0,
        )
    else:
        raise ValueError(f"unknown battery interpretation: {battery_interpretation}")
    plan_cost = float(g @ data.price)
    emergency_cost = float(
        settled["emergency"] @ (K_EMERGENCY * data.price)
    )
    return candidate["candidate_id"], {
        "g": g,
        "settled": settled,
        "cost_yuan": plan_cost + emergency_cost,
        "plan_cost_yuan": plan_cost,
        "emergency_cost_yuan": emergency_cost,
        "solve_seconds": float(diag["solve_seconds"]),
    }


def fingerprint(payload: dict) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def interval_results(data, arrays, load_pred, pv_pred, days) -> pd.DataFrame:
    rows = []
    for day in days:
        for k in range(144):
            rows.append({
                "date": data.dates[day].date().isoformat(),
                "time_index": k,
                "load_actual": float(data.load[day, k]),
                "pv_actual": float(data.pv[day, k]),
                "load_forecast": float(load_pred[day, k]),
                "pv_forecast": float(pv_pred[day, k]),
                "grid_plan": float(arrays["G"][day, k]),
                "charge": float(arrays["C"][day, k]),
                "discharge": float(arrays["D"][day, k]),
                "emergency": float(arrays["Emergency"][day, k]),
                "spill": float(arrays["Spill"][day, k]),
                "soc_before": float(arrays["SOC"][day, k]),
                "soc_after": float(arrays["SOC"][day, k + 1]),
                "price": float(data.price[k]),
                "normal_cost": float(arrays["G"][day, k] * data.price[k]),
                "emergency_cost": float(
                    arrays["Emergency"][day, k] * K_EMERGENCY * data.price[k]
                ),
            })
    return pd.DataFrame(rows)


def main() -> None:
    global OUT, RUNS, SCENARIO_COUNT, TIME_MAPPING
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-day", type=int, default=int(TEST_DAYS[0]))
    parser.add_argument("--end-day", type=int, default=int(TEST_DAYS[-1]))
    parser.add_argument("--output-name", default="ONLINE_RISK_SP")
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--scenario-count", type=int, default=SCENARIO_COUNT)
    parser.add_argument("--initial-soc", type=float, default=E_INIT)
    parser.add_argument(
        "--battery-interpretation",
        choices=["A", "B"],
        default="A",
    )
    parser.add_argument("--scoring-mode", choices=["A", "B"], default="A")
    parser.add_argument("--time-mapping", choices=["A", "B"], default="A")
    parser.add_argument(
        "--workers",
        type=int,
        default=min(15, max(1, (os.cpu_count() or 1) // 2)),
    )
    args = parser.parse_args()
    if args.output_root:
        OUT = Path(args.output_root).resolve()
        RUNS = OUT / "runs"
    SCENARIO_COUNT = int(args.scenario_count)
    TIME_MAPPING = args.time_mapping
    days = TEST_DAYS[(TEST_DAYS >= args.start_day) & (TEST_DAYS <= args.end_day)]
    if not len(days):
        raise SystemExit("empty online-selector day range")
    OUT.mkdir(parents=True, exist_ok=True)
    RUNS.mkdir(parents=True, exist_ok=True)
    data = load_data() if args.time_mapping == "A" else _shifted_data()
    load_fc, pv_fc = build_forecasts(data)
    load_pred = load_fc["same_weekday_2w"]
    pv_pred = pv_fc["recent_5d"]
    candidates = candidate_grid()

    arrays = {key: np.zeros((365, 144)) for key in ("G", "C", "D", "Emergency", "Spill")}
    arrays["SOC"] = np.full((365, 145), np.nan)
    histories: dict[str, list[float]] = {c["candidate_id"]: [] for c in candidates}
    parameter_rows: list[dict] = []
    diagnostics: list[dict] = []
    e0 = float(args.initial_soc)
    started = perf_counter()

    with concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers,
        initializer=_worker_init,
        initargs=(args.time_mapping,),
    ) as executor:
        for position, day in enumerate(days):
            candidate_day: dict[str, dict] = {}
            futures = [
                executor.submit(
                    _solve_candidate,
                    (
                        int(day), e0, candidate, int(SCENARIO_COUNT),
                        args.battery_interpretation,
                    ),
                )
                for candidate in candidates
            ]
            for future in concurrent.futures.as_completed(futures):
                candidate_id, values = future.result()
                candidate_day[candidate_id] = values

            scores = {}
            for candidate in candidates:
                cid = candidate["candidate_id"]
                history = histories[cid][-WINDOW_DAYS:]
                scores[cid] = float(np.mean(history)) if history else None
            default_id = "cvar_t0.90_r0.05_g0.00"
            feasible = {k: v for k, v in scores.items() if v is not None}
            selected_id = min(feasible, key=feasible.get) if feasible else default_id
            selected = candidate_day[selected_id]
            g = selected["g"]
            settled = selected["settled"]

            arrays["G"][day] = g
            arrays["C"][day] = settled["c"]
            arrays["D"][day] = settled["d"]
            arrays["Emergency"][day] = settled["emergency"]
            arrays["Spill"][day] = settled["spill"]
            arrays["SOC"][day] = settled["soc"]
            e0 = float(settled["soc"][-1])

            parameter_rows.append({
                "date": data.dates[day].date().isoformat(),
                "day_index": int(day),
                "selected_candidate": selected_id,
                "selected_tau": next(c["tau"] for c in candidates if c["candidate_id"] == selected_id),
                "selected_rho": next(c["rho"] for c in candidates if c["candidate_id"] == selected_id),
                "selected_gamma": next(c["gamma"] for c in candidates if c["candidate_id"] == selected_id),
                "soc_start_kwh": float(settled["soc"][0]),
                "soc_end_kwh": float(settled["soc"][-1]),
                "realized_total_cost_yuan": float(selected["cost_yuan"]),
                "plan_cost_yuan": float(selected["plan_cost_yuan"]),
                "emergency_cost_yuan": float(selected["emergency_cost_yuan"]),
                "emergency_kwh": float(settled["emergency"].sum()),
                "spill_kwh": float(settled["spill"].sum()),
                "candidate_scores_using_past_only": json.dumps(scores, ensure_ascii=False),
            })
            diagnostics.append({
                "day_index": int(day),
                "candidate_count": len(candidates),
                "total_candidate_solve_seconds": float(
                    sum(v["solve_seconds"] for v in candidate_day.values())
                ),
            })
            for candidate in candidates:
                cid = candidate["candidate_id"]
                record = candidate_day[cid]
                score_value = float(record["cost_yuan"])
                if args.scoring_mode == "B":
                    score_value += TERMINAL_LAMBDA * (
                        6000.0 - float(record["settled"]["soc"][-1])
                    )
                histories[cid].append(score_value)

            if (position + 1) % 5 == 0 or position + 1 == len(days):
                print(
                    f"online selector {position + 1}/{len(days)} "
                    f"selected={selected_id}",
                    flush=True,
                )

    summary = summarize_policy(
        data, arrays, days, perf_counter() - started,
        f"ONLINE-RISK-SP-{args.scoring_mode}-S{args.scenario_count}-"
        f"BAT{args.battery_interpretation}",
    )
    result = summary | {"arrays": arrays}
    save_policy_npz(RUNS / f"{args.output_name}.npz", result)
    (RUNS / f"{args.output_name}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    suffix = "" if args.output_name == "ONLINE_RISK_SP" else f"_{args.output_name}"
    pd.DataFrame(parameter_rows).to_csv(
        OUT / f"online_parameter_path{suffix}.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame([summary]).to_csv(
        OUT / f"online_selector_results{suffix}.csv", index=False, encoding="utf-8-sig"
    )
    interval_results(data, arrays, load_pred, pv_pred, days).to_csv(
        RUNS / f"{args.output_name}_interval.csv", index=False, encoding="utf-8-sig"
    )
    config = {
        "script": Path(__file__).name,
        "selection_window_days": WINDOW_DAYS,
        "scenario_count": SCENARIO_COUNT,
        "scenario_window_days": SCENARIO_WINDOW,
        "terminal_lambda": TERMINAL_LAMBDA,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "default_candidate_before_history": "cvar_t0.90_r0.05_g0.00",
        "daily_decisions_use_same_actual_soc": True,
        "selection_uses_only_prior_realized_costs": True,
        "scoring_mode": args.scoring_mode,
        "time_mapping": args.time_mapping,
        "scenario_count": int(args.scenario_count),
        "start_day": int(days[0]),
        "end_day": int(days[-1]),
        "initial_soc_kwh": float(args.initial_soc),
        "battery_interpretation": args.battery_interpretation,
        "days": int(len(days)),
        "parallel_workers": int(args.workers),
    }
    config["config_hash"] = fingerprint(config)
    (OUT / f"config{suffix}.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / f"solve_diagnostics{suffix}.csv").write_text(
        pd.DataFrame(diagnostics).to_csv(index=False), encoding="utf-8-sig"
    )
    print(json.dumps({k: summary[k] for k in summary if k != "diagnostics"},
                     ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
