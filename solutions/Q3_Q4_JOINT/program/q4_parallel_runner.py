"""Optional candidate parallelism for FUTURE Q4 runs; never attach to a process.

Future run: python q4_parallel_runner.py --workers 4 --mode p1 --run-id NEW_ID
Bounded check: python q4_parallel_runner.py --benchmark --workers 2
Only candidate LPs run in children. Ranking, execution and score maturity retain
the serial policy's order and implementation. No active source files are edited.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from functools import wraps
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import sys
from time import perf_counter

# Imports must not create bytecode in the source-frozen Q2/Q3/Q4 directories.
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "solutions/Q4_V1_ALIGNED/program"))
import numpy as np
import q4_core
import run_q4
from q4_prices import forecast_prices, load_prices
from q4_provenance import upstream_path, verify_q2

_WORKER = None
START_METHOD = "spawn"


def _initialize_worker(data, load_pred, pv_pred):
    global _WORKER
    _WORKER = (data, load_pred, pv_pred)


def _solve_candidate(task):
    day, planned_e0, prices, candidate = task
    data, load_pred, pv_pred = _WORKER
    online, model = q4_core.online, q4_core.model
    load_sc, pv_sc, weights = online._recency_scenarios(
        data, load_pred, pv_pred, day, online.SCENARIO_COUNT,
        online.SCENARIO_WINDOW, candidate["gamma"])
    grid, diagnostics = model.two_stage_plan(
        prices, load_sc, pv_sc, weights, planned_e0,
        terminal="value", terminal_lambda=online.TERMINAL_LAMBDA,
        cvar_beta=candidate["tau"] or 0., cvar_weight=candidate["rho"])
    return candidate["candidate_id"], grid, diagnostics


class ParallelMidnightPolicy(q4_core.MidnightPolicy):
    def __init__(self, data, load_pred, pv_pred, *, executor):
        super().__init__(data, load_pred, pv_pred)
        self.executor = executor

    def plan(self, day, planned_e0, price_forecast):
        online = q4_core.online
        self.pending = online.release_mature_scores(self.pending, self.histories, day)
        scores = {key: float(np.mean(v[-online.WINDOW_DAYS:]))
                  for key, v in self.histories.items() if v}
        selected = min(scores, key=scores.get) if scores else online.DEFAULT_CANDIDATE
        tasks = [(day, planned_e0, price_forecast.values, candidate)
                 for candidate in self.candidates]
        plans, diagnostics = {}, {}
        # map yields in submission order, independent of child completion order.
        for candidate, result in zip(self.candidates, self.executor.map(_solve_candidate, tasks, chunksize=1)):
            key, grid, diag = result
            if key != candidate["candidate_id"]:
                raise RuntimeError("candidate identity/order mismatch")
            plans[key], diagnostics[key] = grid, diag
        return selected, plans, {"scores": scores, "solver": diagnostics}


class PolicyFactory:
    """One persistent pool for a run, separate scoring histories per trajectory."""

    def __init__(self, workers):
        if not 1 <= workers <= 15:
            raise ValueError("workers must be between 1 and 15")
        self.workers, self.executor, self.inputs = workers, None, None

    def __call__(self, data, load_pred, pv_pred):
        values = (data, load_pred, pv_pred)
        if self.executor is None:
            self.inputs = values
            self.executor = ProcessPoolExecutor(
                max_workers=self.workers, mp_context=multiprocessing.get_context(START_METHOD),
                initializer=_initialize_worker, initargs=values)
        elif any(a is not b for a, b in zip(values, self.inputs)):
            raise ValueError("a shared pool requires the same immutable input objects")
        return ParallelMidnightPolicy(*values, executor=self.executor)

    def close(self):
        if self.executor is not None:
            self.executor.shutdown(wait=True, cancel_futures=True)


@contextmanager
def parallel_backend(workers):
    """Patch this interpreter only and include the sidecar in future provenance."""
    factory = PolicyFactory(workers)
    original_policy = run_q4.MidnightPolicy
    original_q42, original_q43 = run_q4.q42, run_q4.q43
    original_snapshot, original_write = run_q4.source_snapshot, run_q4.write_json
    run_directory, initial_manifest = None, None
    wrapper = Path(__file__).resolve()
    source = wrapper.read_bytes()
    source_hash = hashlib.sha256(source).hexdigest()
    config = {
        "name": "ProcessPoolExecutor_candidate_LPs", "workers": workers,
        "start_method": START_METHOD, "chunksize": 1,
        "result_order": "frozen_candidate_submission_order",
        "state_and_score_execution": "original_serial_parent",
        "wrapper_source_path": str(wrapper.relative_to(ROOT)),
        "wrapper_source_sha256": source_hash,
        "wrapper_source_snapshot": "q4_parallel_runner.py",
        "solver_options": "unchanged_Q2_two_stage_plan",
        "thread_environment": {name: os.environ.get(name) for name in
            ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "HIGHS_THREADS")},
        "applies_to": "this_new_run_only",
        "completed_trajectory_checkpoints": "parallel_checkpoints/<trajectory>",
    }

    def snapshot():
        return {**original_snapshot(), str(wrapper.relative_to(ROOT)):
                hashlib.sha256(wrapper.read_bytes()).hexdigest()}

    def write(path, value):
        nonlocal run_directory, initial_manifest
        if Path(path).name == "manifest.json":
            snapshot_path = Path(path).parent / config["wrapper_source_snapshot"]
            if not Path(path).exists():
                run_directory, initial_manifest = Path(path).parent, dict(value)
                with snapshot_path.open("xb") as handle:
                    handle.write(source)
            value = {**value, "execution_backend": config}
        return original_write(path, value)

    def checkpoint(name, result, filenames):
        if run_directory is None:
            raise RuntimeError("checkpoint requires the new run's initial manifest")
        directory = run_directory / "parallel_checkpoints" / name
        directory.mkdir(parents=True, exist_ok=False)
        for frame, filename in zip(result, filenames):
            frame.to_csv(directory / filename, index=False, mode="x")
        metadata = {
            "status": "trajectory_returned_overall_run_not_yet_complete",
            "formal_use": False, "trajectory": name, "execution_backend": config,
            "source_hashes": initial_manifest["source_hashes"],
            "input_hashes": initial_manifest["input_hashes"],
            "outputs": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted(directory.glob("*.csv"))},
        }
        with (directory / "checkpoint_manifest.json").open("x", encoding="utf-8") as handle:
            json.dump(metadata, handle, ensure_ascii=False, indent=2)

    @wraps(original_q42)
    def q42(*args, **kwargs):
        result = original_q42(*args, **kwargs)
        checkpoint("q4_2", result, ("all_intervals.csv", "candidates.csv"))
        return result

    @wraps(original_q43)
    def q43(*args, **kwargs):
        result = original_q43(*args, **kwargs)
        settlement = kwargs.get("settlement", args[5] if len(args) > 5 else None)
        if settlement not in ("A", "B"):
            raise ValueError("unknown Q4-3 checkpoint settlement")
        checkpoint(f"q4_3_{settlement}", result, ("all_intervals.csv", "adjustments.csv",
                   "candidates.csv", "price_forecasts.csv", "plans.csv"))
        return result

    run_q4.MidnightPolicy, run_q4.source_snapshot, run_q4.write_json = factory, snapshot, write
    run_q4.q42, run_q4.q43 = q42, q43
    try:
        yield factory
    finally:
        run_q4.MidnightPolicy = original_policy
        run_q4.q42, run_q4.q43 = original_q42, original_q43
        run_q4.source_snapshot, run_q4.write_json = original_snapshot, original_write
        factory.close()


def benchmark(workers=2, start_day=78, days=3):
    """Bounded real-data equivalence, NOT a historical or annual policy result."""
    if not 2 <= days <= 3 or not 31 <= start_day <= 364-days:
        raise ValueError("benchmark requires 2-3 mature real days inside the year")
    frozen = run_q4.source_snapshot()
    verify_q2()
    data = q4_core.model.load_data()
    with np.load(upstream_path() / "forecast_bundle.npz", allow_pickle=False) as bundle:
        load_pred, pv_pred = bundle["load_b0"].copy(), bundle["pv_b0"].copy()
    prices = load_prices(ROOT / "data/附件4.xlsx", data.dates)
    serial = q4_core.MidnightPolicy(data, load_pred, pv_pred)
    factory = PolicyFactory(workers)
    parallel = factory(data, load_pred, pv_pred)
    rows, selected_ids = [], []
    planned_e0, executed_e0 = 6000., 6000.
    max_difference = 0.
    try:
        for offset, day in enumerate(range(start_day, start_day+days)):
            forecast = forecast_prices(data.dates, prices, data.price, day, data.dates[day])
            # Alternate order to reduce systematic cache/load bias.
            results, timings = {}, {}
            order = (("serial", serial), ("parallel", parallel))
            for name, policy in (order if offset % 2 == 0 else order[::-1]):
                began = perf_counter()
                results[name] = policy.plan(day, planned_e0, forecast)
                timings[name] = perf_counter()-began
            a, b = results["serial"], results["parallel"]
            assert a[0] == b[0] and a[2]["scores"] == b[2]["scores"]
            assert list(a[1]) == list(b[1]) == [c["candidate_id"] for c in serial.candidates]
            for key in a[1]:
                difference = float(np.max(abs(a[1][key]-b[1][key])))
                max_difference = max(max_difference, difference)
                np.testing.assert_array_equal(a[1][key], b[1][key])
                da = {k:v for k,v in a[2]["solver"][key].items() if k != "solve_seconds"}
                db = {k:v for k,v in b[2]["solver"][key].items() if k != "solve_seconds"}
                assert da == db
            for name, policy in order:
                policy.settle_candidate_scores(day, results[name][1], executed_e0, prices[day])
            assert serial.pending == parallel.pending and serial.histories == parallel.histories
            assert len(next(iter(serial.histories.values()))) == max(0, offset-1)
            settled_a = q4_core.model.settle_causally(a[1][a[0]], data.load[day], data.pv[day], executed_e0)
            settled_b = q4_core.model.settle_causally(b[1][b[0]], data.load[day], data.pv[day], executed_e0)
            for key in settled_a:
                np.testing.assert_array_equal(settled_a[key], settled_b[key])
            grid = a[1][a[0]]
            planned_e0 = q4_core.online.project_pending_energy(
                settled_a["soc"][-2], grid[-1], load_pred[day,-1], pv_pred[day,-1])
            executed_e0 = float(settled_a["soc"][-1])
            selected_ids.append(a[0])
            rows.append({"day_index": day, **timings})
            print(json.dumps(rows[-1]), flush=True)
    finally:
        factory.close()
    assert run_q4.source_snapshot() == frozen
    serial_total = sum(row["serial"] for row in rows)
    parallel_total = sum(row["parallel"] for row in rows)
    return {"status": "bounded_equivalence_passed", "days": rows,
        "workers": workers, "candidate_count": 15, "scenario_count": 10,
        "max_grid_difference_kwh": max_difference, "selected_ids": selected_ids,
        "serial_seconds": serial_total, "parallel_seconds_including_spawn": parallel_total,
        "speedup_including_spawn": serial_total/parallel_total,
        "steady_day_speedup": sum(r["serial"] for r in rows[1:])/sum(r["parallel"] for r in rows[1:]),
        "active_sources_unchanged": True, "annual_run": False,
        "qualification": "local concurrent-machine timing; 6000 kWh diagnostic start and initially empty candidate history, not an annual result"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--benchmark-day", type=int, default=78)
    parser.add_argument("--benchmark-days", type=int, default=3)
    options, remaining = parser.parse_known_args()
    if options.benchmark:
        if remaining:
            parser.error("unexpected benchmark arguments")
        print(json.dumps(benchmark(options.workers, options.benchmark_day, options.benchmark_days), indent=2))
    else:
        args = run_q4.parser().parse_args(remaining)
        with parallel_backend(options.workers):
            print(run_q4.run(args))


if __name__ == "__main__":
    main()
