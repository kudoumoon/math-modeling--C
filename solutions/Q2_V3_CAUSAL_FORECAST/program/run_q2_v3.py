"""Run one frozen Q2 V3 forecast arm through the ONLINE-RISK-SP policy."""

from __future__ import annotations

import argparse
import concurrent.futures
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter

import numpy as np
import pandas as pd

from q2_forecasts import (
    ARM_MODEL_IDS,
    HGB_PARAMETERS,
    build_forecast_bundle,
    build_b0_time_b_forecasts,
    shift_cross_day,
)
from q2_model import (
    DT,
    E_INIT,
    E_MAX,
    E_MIN,
    K_EMERGENCY,
    Q_MAX,
    Q2Data,
    load_data,
    plan_battery_for_fixed_grid,
    save_policy_npz,
    settle_causally,
    settle_one_slot_delayed,
    settle_planned_battery,
    summarize_policy,
    two_stage_plan,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
VERSION_ROOT = Path(__file__).resolve().parents[1]
WINDOW_DAYS = 28
SCENARIO_COUNT = 10
SCENARIO_WINDOW = 60
TERMINAL_LAMBDA = 0.4684
DEFAULT_CANDIDATE = "cvar_t0.90_r0.05_g0.00"
_WORKER: dict = {}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def candidate_grid() -> list[dict]:
    candidates = []
    for gamma in (0.0, 0.02, 0.05):
        candidates.append({
            "candidate_id": f"nocvar_g{gamma:.2f}",
            "tau": None,
            "rho": 0.0,
            "gamma": gamma,
        })
        for tau in (0.90, 0.95):
            for rho in (0.05, 0.20):
                candidates.append({
                    "candidate_id": f"cvar_t{tau:.2f}_r{rho:.2f}_g{gamma:.2f}",
                    "tau": tau,
                    "rho": rho,
                    "gamma": gamma,
                })
    return candidates


def _recency_scenarios(
    data: Q2Data,
    load_pred: np.ndarray,
    pv_pred: np.ndarray,
    day: int,
    count: int,
    window: int,
    gamma: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    # At day d 00:00, plan-day d-1 still has one unfinished interval.
    stop = max(0, day - 1)
    indexes = np.arange(max(0, day - window), stop, dtype=int)
    valid = (
        ~np.isnan(load_pred[indexes]).any(axis=1)
        & ~np.isnan(pv_pred[indexes]).any(axis=1)
    ) if len(indexes) else np.array([], dtype=bool)
    indexes = indexes[valid]
    if len(indexes) == 0:
        return load_pred[day][None, :], pv_pred[day][None, :], np.ones(1)
    chosen = indexes[
        np.linspace(0, len(indexes) - 1, min(count, len(indexes))).astype(int)
    ]
    age = day - chosen
    weights = np.exp(-gamma * age)
    weights = weights / weights.sum()
    load = np.maximum(
        load_pred[day] + data.load[chosen] - load_pred[chosen], 0.0
    )
    pv = np.maximum(
        pv_pred[day] + data.pv[chosen] - pv_pred[chosen], 0.0
    )
    pv[:, pv_pred[day] <= 1e-9] = 0.0
    return load, pv, weights


def _worker_init(
    data: Q2Data,
    load_pred: np.ndarray,
    pv_pred: np.ndarray,
    battery_interpretation: str,
    observation_delay_slots: int,
) -> None:
    _WORKER["data"] = data
    _WORKER["load_pred"] = load_pred
    _WORKER["pv_pred"] = pv_pred
    _WORKER["battery_interpretation"] = battery_interpretation
    _WORKER["observation_delay_slots"] = observation_delay_slots


def _solve_candidate(task: tuple[int, float, float, dict, int]) -> tuple[str, dict]:
    day, planned_e0, executed_e0, candidate, scenario_count = task
    data = _WORKER["data"]
    load_pred = _WORKER["load_pred"]
    pv_pred = _WORKER["pv_pred"]
    load_sc, pv_sc, weights = _recency_scenarios(
        data, load_pred, pv_pred, day, scenario_count, SCENARIO_WINDOW,
        candidate["gamma"],
    )
    grid, diagnostics = two_stage_plan(
        data.price,
        load_sc,
        pv_sc,
        weights,
        planned_e0,
        terminal="value",
        terminal_lambda=TERMINAL_LAMBDA,
        cvar_beta=candidate["tau"] or 0.0,
        cvar_weight=candidate["rho"],
    )
    if _WORKER["battery_interpretation"] == "A":
        battery_plan = None
        if _WORKER["observation_delay_slots"] == 0:
            settled = settle_causally(
                grid, data.load[day], data.pv[day], executed_e0
            )
        else:
            settled = settle_one_slot_delayed(
                grid,
                data.load[day],
                data.pv[day],
                load_pred[day],
                pv_pred[day],
                executed_e0,
                None if day == 0 else float(data.load[day - 1, -1]),
                None if day == 0 else float(data.pv[day - 1, -1]),
            )
    else:
        expected_load = np.average(load_sc, axis=0, weights=weights)
        expected_pv = np.average(pv_sc, axis=0, weights=weights)
        battery_plan = plan_battery_for_fixed_grid(
            data.price,
            expected_load,
            expected_pv,
            planned_e0,
            grid,
            terminal="value",
            terminal_lambda=TERMINAL_LAMBDA,
        )
        settled = settle_planned_battery(
            grid,
            battery_plan["c"],
            battery_plan["d"],
            data.load[day],
            data.pv[day],
            executed_e0,
        )
    plan_cost = float(grid @ data.price)
    emergency_cost = float(settled["emergency"] @ (K_EMERGENCY * data.price))
    return candidate["candidate_id"], {
        "grid": grid,
        "settled": settled,
        "plan_cost_yuan": plan_cost,
        "emergency_cost_yuan": emergency_cost,
        "cost_yuan": plan_cost + emergency_cost,
        "solve_seconds": float(diagnostics["solve_seconds"]),
        "max_source_pool_residual": float(
            diagnostics["max_source_pool_residual"]
        ),
        "pending_charge_plan_kwh": (
            None if battery_plan is None else float(battery_plan["c"][-1])
        ),
        "pending_discharge_plan_kwh": (
            None if battery_plan is None else float(battery_plan["d"][-1])
        ),
        "commanded_c": (
            settled.get("commanded_c")
            if "commanded_c" in settled
            else (battery_plan["c"] if battery_plan is not None else settled["c"])
        ),
        "commanded_d": (
            settled.get("commanded_d")
            if "commanded_d" in settled
            else (battery_plan["d"] if battery_plan is not None else settled["d"])
        ),
    }


def project_pending_energy(
    energy_before: float,
    grid_kwh: float,
    load_forecast_kw: float,
    pv_forecast_kw: float,
) -> float:
    balance = grid_kwh + pv_forecast_kw * DT - load_forecast_kw * DT
    if balance >= 0.0:
        charge = min(
            balance, Q_MAX, max(0.0, (E_MAX - energy_before) / 0.9)
        )
        return float(energy_before + 0.9 * charge)
    discharge = min(
        -balance, Q_MAX, max(0.0, 0.9 * (energy_before - E_MIN))
    )
    return float(energy_before - discharge / 0.9)


def project_planned_pending_energy(
    energy_before: float,
    grid_kwh: float,
    load_forecast_kw: float,
    pv_forecast_kw: float,
    charge_plan_kwh: float,
    discharge_plan_kwh: float,
) -> float:
    """Project Battery B with its frozen action under forecast feasibility."""
    normal_supply = grid_kwh + pv_forecast_kw * DT
    demand = load_forecast_kw * DT
    if normal_supply >= demand:
        charge = min(
            max(charge_plan_kwh, 0.0),
            normal_supply - demand,
            Q_MAX,
            max(0.0, (E_MAX - energy_before) / 0.9),
        )
        return float(energy_before + 0.9 * charge)
    discharge = min(
        max(discharge_plan_kwh, 0.0),
        demand - normal_supply,
        Q_MAX,
        max(0.0, 0.9 * (energy_before - E_MIN)),
    )
    return float(energy_before - discharge / 0.9)


def project_delayed_pending_energy(
    energy_before: float,
    grid_kwh: float,
    observed_load_kw: float,
    observed_pv_kw: float,
    pending_load_forecast_kw: float,
    pending_pv_forecast_kw: float,
) -> float:
    """Project the pending interval using the one-slot-delayed control law."""
    observed_balance = grid_kwh + observed_pv_kw * DT - observed_load_kw * DT
    desired_charge = min(
        max(observed_balance, 0.0), Q_MAX,
        max(0.0, (E_MAX - energy_before) / 0.9),
    )
    desired_discharge = min(
        max(-observed_balance, 0.0), Q_MAX,
        max(0.0, 0.9 * (energy_before - E_MIN)),
    )
    forecast_balance = (
        grid_kwh + pending_pv_forecast_kw * DT
        - pending_load_forecast_kw * DT
    )
    if forecast_balance >= 0.0:
        return float(energy_before + 0.9 * min(desired_charge, forecast_balance))
    return float(
        energy_before - min(desired_discharge, -forecast_balance) / 0.9
    )


def release_mature_scores(
    pending_scores: list[tuple[int, dict[str, float]]],
    histories: dict[str, list[float]],
    day: int,
) -> list[tuple[int, dict[str, float]]]:
    retained = []
    for source_day, scores in pending_scores:
        if source_day <= day - 2:
            for candidate_id, score in scores.items():
                histories[candidate_id].append(score)
        else:
            retained.append((source_day, scores))
    return retained


def _daily_rows(
    data: Q2Data,
    arrays: dict[str, np.ndarray],
    parameters: list[dict],
) -> pd.DataFrame:
    by_day = {row["day_index"]: row for row in parameters}
    rows = []
    for day in sorted(by_day):
        meta = by_day[day]
        rows.append({
            **meta,
            "grid_purchase_kwh": float(arrays["G"][day].sum()),
            "emergency_kwh": float(arrays["Emergency"][day].sum()),
            "spill_kwh": float(arrays["Spill"][day].sum()),
            "charge_kwh": float(arrays["C"][day].sum()),
            "discharge_kwh": float(arrays["D"][day].sum()),
            "commanded_charge_kwh": float(arrays["CommandedC"][day].sum()),
            "commanded_discharge_kwh": float(arrays["CommandedD"][day].sum()),
        })
    return pd.DataFrame(rows)


def _interval_rows(
    data: Q2Data,
    arrays: dict[str, np.ndarray],
    load_pred: np.ndarray,
    pv_pred: np.ndarray,
    days: np.ndarray,
    arm: str,
) -> pd.DataFrame:
    rows = []
    for day in days:
        date = data.dates[day]
        for slot in range(144):
            start = date + pd.Timedelta(minutes=(slot + 1) * 10)
            rows.append({
                "plan_day": date.date().isoformat(),
                "issue_time": date.isoformat(),
                "interval_start": start.isoformat(),
                "interval_end": (start + pd.Timedelta(minutes=10)).isoformat(),
                "time_index": slot,
                "forecast_arm": arm,
                "forecast_model_id": ARM_MODEL_IDS[arm],
                "load_forecast_kw": float(load_pred[day, slot]),
                "pv_forecast_kw": float(pv_pred[day, slot]),
                "load_actual_kw": float(data.load[day, slot]),
                "pv_actual_kw": float(data.pv[day, slot]),
                "planned_grid_kwh": float(arrays["G"][day, slot]),
                "charge_kwh": float(arrays["C"][day, slot]),
                "discharge_kwh": float(arrays["D"][day, slot]),
                "commanded_charge_kwh": float(arrays["CommandedC"][day, slot]),
                "commanded_discharge_kwh": float(arrays["CommandedD"][day, slot]),
                "emergency_kwh": float(arrays["Emergency"][day, slot]),
                "unused_supply_kwh": float(arrays["Spill"][day, slot]),
                "actual_soc_before_kwh": float(arrays["SOC"][day, slot]),
                "actual_soc_after_kwh": float(arrays["SOC"][day, slot + 1]),
                "price_yuan_per_kwh": float(data.price[slot]),
                "plan_cost_yuan": float(
                    arrays["G"][day, slot] * data.price[slot]
                ),
                "emergency_cost_yuan": float(
                    arrays["Emergency"][day, slot]
                    * K_EMERGENCY
                    * data.price[slot]
                ),
            })
    return pd.DataFrame(rows)


def run(args: argparse.Namespace) -> Path:
    run_root = Path(args.output_root).resolve()
    run_root.mkdir(parents=True, exist_ok=False)
    manifest_path = run_root / "manifest.json"
    started = perf_counter()
    source_paths = [
        Path(__file__),
        Path(__file__).with_name("q2_forecasts.py"),
        Path(__file__).with_name("q2_model.py"),
        Path(__file__).with_name("q2_deep_core.py"),
    ]
    input_paths = [
        REPO_ROOT / "data/附件1.xlsx",
        REPO_ROOT / "data/附件2.xlsx",
        REPO_ROOT / "data/附件5/result2.xlsx",
    ]
    manifest = {
        "schema_version": 1,
        "status": "running",
        "run_id": args.run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip(),
        "command": sys.argv,
        "source_hashes": {
            str(path.relative_to(REPO_ROOT)): sha256(path)
            for path in source_paths
        },
        "input_hashes": {
            str(path.relative_to(REPO_ROOT)): sha256(path)
            for path in input_paths
        },
        "python": sys.version,
        "platform": platform.platform(),
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "pandas", "scipy", "scikit-learn", "openpyxl")
        },
    }
    write_json(manifest_path, manifest)
    try:
        data = load_data()
        bundle = build_forecast_bundle(data, required_arm=args.arm)
        load_pred, pv_pred = bundle.for_arm(args.arm)
        if args.time_mapping == "B":
            if args.end_day >= len(data.dates) - 1:
                raise ValueError("time mapping B cannot include 2025-12-31")
            if args.arm != "B0":
                raise ValueError("time mapping B sensitivity is frozen to selected arm B0")
            load_pred, pv_pred = build_b0_time_b_forecasts(data)
            data = replace(
                data,
                price=shift_cross_day(np.tile(data.price, (365, 1)))[0],
                load=shift_cross_day(data.load),
                pv=shift_cross_day(data.pv),
            )
        days = np.arange(args.start_day, args.end_day + 1, dtype=int)
        report_days = days[days >= args.report_start_day]
        if len(days) == 0 or len(report_days) == 0:
            raise ValueError("run and report day ranges must be non-empty")
        if args.start_day != 0:
            raise ValueError("continuous Q2 V3 runs must start on January 1")
        if args.battery_interpretation == "B" and args.observation_delay_slots:
            raise ValueError("observation-delay sensitivity applies only to Battery A")

        candidates = candidate_grid()
        arrays = {
            key: np.zeros((365, 144))
            for key in (
                "G", "C", "D", "CommandedC", "CommandedD",
                "Emergency", "Spill",
            )
        }
        arrays["SOC"] = np.full((365, 145), np.nan)
        histories = {item["candidate_id"]: [] for item in candidates}
        pending_scores: list[tuple[int, dict[str, float]]] = []
        parameter_rows: list[dict] = []
        diagnostic_rows: list[dict] = []
        planned_e0 = float(args.initial_soc)
        executed_e0 = float(args.initial_soc)

        with concurrent.futures.ProcessPoolExecutor(
            max_workers=args.workers,
            initializer=_worker_init,
            initargs=(
                data,
                load_pred,
                pv_pred,
                args.battery_interpretation,
                args.observation_delay_slots,
            ),
        ) as executor:
            for position, day in enumerate(days):
                if args.compatibility_reset and day == args.report_start_day:
                    planned_e0 = float(args.initial_soc)
                    executed_e0 = float(args.initial_soc)
                pending_scores = release_mature_scores(
                    pending_scores, histories, int(day)
                )

                futures = [
                    executor.submit(
                        _solve_candidate,
                        (
                            int(day),
                            planned_e0,
                            executed_e0,
                            candidate,
                            args.scenario_count,
                        ),
                    )
                    for candidate in candidates
                ]
                solved = {}
                for future in concurrent.futures.as_completed(futures):
                    candidate_id, result = future.result()
                    solved[candidate_id] = result

                scores = {
                    candidate_id: (
                        float(np.mean(values[-WINDOW_DAYS:]))
                        if values else None
                    )
                    for candidate_id, values in histories.items()
                }
                feasible = {
                    key: value for key, value in scores.items()
                    if value is not None
                }
                selected_id = (
                    min(feasible, key=feasible.get)
                    if feasible else DEFAULT_CANDIDATE
                )
                selected = solved[selected_id]
                settled = selected["settled"]
                for source, target in (
                    ("grid", "G"),
                    ("c", "C"),
                    ("d", "D"),
                    ("emergency", "Emergency"),
                    ("spill", "Spill"),
                    ("commanded_c", "CommandedC"),
                    ("commanded_d", "CommandedD"),
                ):
                    values = (
                        selected[source]
                        if source in {"grid", "commanded_c", "commanded_d"}
                        else settled[source]
                    )
                    arrays[target][day] = values
                arrays["SOC"][day] = settled["soc"]

                parameter_rows.append({
                    "date": data.dates[day].date().isoformat(),
                    "day_index": int(day),
                    "selected_candidate": selected_id,
                    "planned_initial_energy_kwh": planned_e0,
                    "executed_initial_energy_kwh": executed_e0,
                    "actual_end_energy_kwh": float(settled["soc"][-1]),
                    "realized_total_cost_yuan": selected["cost_yuan"],
                    "plan_cost_yuan": selected["plan_cost_yuan"],
                    "emergency_cost_yuan": selected["emergency_cost_yuan"],
                    "candidate_scores_completed_before_issue": json.dumps(
                        scores, ensure_ascii=False
                    ),
                    "latest_full_score_day_released": int(day - 2),
                })
                diagnostic_rows.append({
                    "day_index": int(day),
                    "candidate_count": len(solved),
                    "candidate_solve_seconds_sum": float(sum(
                        value["solve_seconds"] for value in solved.values()
                    )),
                    "max_source_pool_residual": float(max(
                        value["max_source_pool_residual"]
                        for value in solved.values()
                    )),
                })
                pending_scores.append((
                    int(day),
                    {
                        candidate_id: (
                            result["cost_yuan"]
                            + (
                                TERMINAL_LAMBDA
                                * (
                                    6000.0
                                    - float(result["settled"]["soc"][-1])
                                )
                                if args.scoring_mode == "B" else 0.0
                            )
                        )
                        for candidate_id, result in solved.items()
                    },
                ))
                if (
                    args.battery_interpretation == "A"
                    and args.observation_delay_slots == 0
                ):
                    planned_e0 = project_pending_energy(
                        float(settled["soc"][-2]),
                        float(selected["grid"][-1]),
                        float(load_pred[day, -1]),
                        float(pv_pred[day, -1]),
                    )
                elif args.battery_interpretation == "B":
                    planned_e0 = project_planned_pending_energy(
                        float(settled["soc"][-2]),
                        float(selected["grid"][-1]),
                        float(load_pred[day, -1]),
                        float(pv_pred[day, -1]),
                        float(selected["pending_charge_plan_kwh"]),
                        float(selected["pending_discharge_plan_kwh"]),
                    )
                else:
                    planned_e0 = project_delayed_pending_energy(
                        float(settled["soc"][-2]),
                        float(selected["grid"][-1]),
                        float(data.load[day, -2]),
                        float(data.pv[day, -2]),
                        float(load_pred[day, -1]),
                        float(pv_pred[day, -1]),
                    )
                executed_e0 = float(settled["soc"][-1])
                if (position + 1) % 5 == 0 or position + 1 == len(days):
                    print(
                        f"{args.arm} {position + 1}/{len(days)} "
                        f"selected={selected_id}",
                        flush=True,
                    )

        summary = summarize_policy(
            data,
            arrays,
            report_days,
            perf_counter() - started,
            (
                f"ONLINE-RISK-SP-{args.scoring_mode}-S{args.scenario_count}-"
                f"TIME{args.time_mapping}-BAT{args.battery_interpretation}-"
                f"OBS{args.observation_delay_slots}-RESET{int(args.compatibility_reset)}-"
                f"{ARM_MODEL_IDS[args.arm]}"
            ),
        )
        january_days = days[days < 31]
        january_summary = (
            summarize_policy(data, arrays, january_days, 0.0, "JANUARY_WARMUP")
            if len(january_days) else None
        )
        config = {
            "run_id": args.run_id,
            "forecast_arm": args.arm,
            "forecast_model_id": ARM_MODEL_IDS[args.arm],
            "hgb_parameters": HGB_PARAMETERS,
            "trained_hgb_channels": sorted(
                bundle.fit_log["target_name"].unique().tolist()
            ) if len(bundle.fit_log) else [],
            "start_day": int(days[0]),
            "end_day": int(days[-1]),
            "report_start_day": int(report_days[0]),
            "report_end_day": int(report_days[-1]),
            "initial_soc_kwh": args.initial_soc,
            "time_mapping": args.time_mapping,
            "battery_interpretation": args.battery_interpretation,
            "observation_delay_slots": args.observation_delay_slots,
            "battery_A_observation_contract": (
                (
                    "within-interval continuous feedback represented by interval averages"
                    if args.observation_delay_slots == 0
                    else "command uses one-slot-delayed measurement; inverter protection clips magnitude using current physical feasibility without changing command direction"
                )
                if args.battery_interpretation == "A"
                else None
            ),
            "scoring_mode": args.scoring_mode,
            "selection_window_days": WINDOW_DAYS,
            "scenario_count": args.scenario_count,
            "scenario_window_days": SCENARIO_WINDOW,
            "terminal_lambda_yuan_per_kwh": TERMINAL_LAMBDA,
            "default_candidate": DEFAULT_CANDIDATE,
            "candidate_grid": candidates,
            "candidate_full_score_delay_days": 2,
            "scenario_latest_complete_plan_day": "day_index - 2",
            "compatibility_reset_on_report_start": args.compatibility_reset,
            "workers": args.workers,
        }
        write_json(run_root / "config.json", config)
        write_json(run_root / "summary.json", summary)
        if january_summary is not None:
            write_json(run_root / "january_warmup_summary.json", january_summary)
        bundle.fit_log.to_csv(run_root / "forecast_fit_log.csv", index=False)
        np.savez_compressed(
            run_root / "forecast_bundle.npz",
            load_b0=bundle.load_b0,
            pv_b0=bundle.pv_b0,
            load_hgb=bundle.load_hgb,
            pv_hgb=bundle.pv_hgb,
        )
        save_policy_npz(run_root / "policy_arrays.npz", {"arrays": arrays})
        daily = _daily_rows(data, arrays, parameter_rows)
        daily.to_csv(run_root / "daily_ledger.csv", index=False)
        _interval_rows(
            data, arrays, load_pred, pv_pred, report_days, args.arm
        ).to_csv(run_root / "interval_ledger.csv", index=False)
        pd.DataFrame(diagnostic_rows).to_csv(
            run_root / "solve_diagnostics.csv", index=False
        )
        manifest["status"] = "complete"
        manifest["configuration"] = config
        manifest["summary"] = summary
        manifest["outputs"] = {
            str(path.relative_to(run_root)): sha256(path)
            for path in sorted(run_root.iterdir())
            if path.is_file() and path != manifest_path
        }
    except BaseException as exc:
        manifest["status"] = "failed"
        manifest["error"] = repr(exc)
        raise
    finally:
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        manifest["elapsed_seconds"] = perf_counter() - started
        write_json(manifest_path, manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return run_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument(
        "--arm", choices=list(ARM_MODEL_IDS), default="B0"
    )
    parser.add_argument("--start-day", type=int, default=0)
    parser.add_argument("--end-day", type=int, default=364)
    parser.add_argument("--report-start-day", type=int, default=31)
    parser.add_argument("--initial-soc", type=float, default=E_INIT)
    parser.add_argument("--scenario-count", type=int, default=SCENARIO_COUNT)
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--time-mapping", choices=["A", "B"], default="A")
    parser.add_argument(
        "--battery-interpretation", choices=["A", "B"], default="A"
    )
    parser.add_argument("--observation-delay-slots", choices=[0, 1], type=int, default=0)
    parser.add_argument("--scoring-mode", choices=["A", "B"], default="A")
    parser.add_argument("--compatibility-reset", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
