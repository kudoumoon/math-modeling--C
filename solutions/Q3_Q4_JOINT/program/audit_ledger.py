"""Independently reconstruct published transactions without running a solver."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]


def audit(path: Path, question: str) -> dict:
    frame = pd.read_csv(path)
    if "final_grid_kwh" in frame and "qfinal_kwh" not in frame:
        frame = frame.rename(columns={
            "final_grid_kwh": "qfinal_kwh", "up_kwh": "u_kwh", "down_kwh": "r_kwh",
            "actual_soc_before_kwh": "soc_before_kwh", "actual_soc_after_kwh": "soc_after_kwh",
            "price_actual_yuan_per_kwh": "price_yuan_per_kwh", "cash_cost_yuan": "total_cost_yuan",
            "settlement_rule": "settlement",
        })
        frame["q0_kwh"] = frame.planned_grid_kwh
        frame["load_actual_kwh"] = frame.load_actual_kw / 6
        frame["pv_actual_kwh"] = frame.pv_actual_kw / 6
    if "day_index" not in frame:
        frame["day_index"] = (pd.to_datetime(frame.plan_day)-pd.Timestamp("2025-01-01")).dt.days
    frame = frame.loc[frame.day_index.between(31, 364)].copy()
    checks = {}
    residuals = {}

    def equal(name, actual, expected, tolerance=1e-7):
        actual, expected = np.asarray(actual), np.asarray(expected)
        error = float(np.max(np.abs(actual - expected)))
        residuals[name] = error
        checks[name] = bool(np.isfinite(error) and error <= tolerance)

    checks["official_rows"] = len(frame) == 334 * 144
    if not checks["official_rows"]:
        return {"passed": False, "checks": checks, "rows": len(frame)}
    days = np.repeat(np.arange(31, 365), 144)
    slots = np.tile(np.arange(144), 334)
    checks["ordered_unique_keys"] = bool(np.array_equal(frame.day_index, days) and np.array_equal(frame.time_index, slots))
    dates = pd.Timestamp("2025-01-01") + pd.to_timedelta(days, unit="D")
    starts = dates + pd.to_timedelta((slots + 1) * 10, unit="min")
    checks["interval_start_mapping_A"] = bool(np.array_equal(pd.to_datetime(frame.interval_start, format="ISO8601", errors="coerce"), starts))
    checks["interval_end_mapping_A"] = bool(np.array_equal(pd.to_datetime(frame.interval_end, format="ISO8601", errors="coerce"), starts + pd.Timedelta(minutes=10)))
    checks["plan_dates"] = bool(np.array_equal(pd.to_datetime(frame.plan_day), dates))
    sheet_load = pd.read_excel(ROOT / "data/附件2.xlsx", sheet_name=0).iloc[:, 1:].to_numpy(float)
    sheet_pv = pd.read_excel(ROOT / "data/附件2.xlsx", sheet_name=1).iloc[:, 1:].to_numpy(float)
    equal("load_matches_attachment", frame.load_actual_kwh, sheet_load[days, slots] / 6)
    equal("pv_matches_attachment", frame.pv_actual_kwh, sheet_pv[days, slots] / 6)
    if question == "Q3":
        p = pd.read_excel(ROOT / "data/附件1.xlsx").iloc[:, 1].to_numpy(float)[slots]
        with np.load(ROOT / "solutions/Q3_Q4_JOINT/results/q2_provisional/policy_arrays.npz") as upstream:
            equal("q0_matches_Q2_G", frame.q0_kwh, upstream["G"][days, slots])
    else:
        p = pd.read_excel(ROOT / "data/附件4.xlsx").iloc[:, 1:].to_numpy(float)[days, slots]
    equal("settlement_price_matches_attachment", frame.price_yuan_per_kwh, p)
    q0, q, c, d, h, w = (frame[k].to_numpy(float) for k in (
        "q0_kwh", "qfinal_kwh", "charge_kwh", "discharge_kwh", "emergency_kwh", "unused_supply_kwh"))
    e0, e1 = frame.soc_before_kwh.to_numpy(float), frame.soc_after_kwh.to_numpy(float)
    u, r = np.maximum(q-q0, 0), np.maximum(q0-q, 0)
    equal("up_quantity", frame.u_kwh, u)
    equal("down_quantity", frame.r_kwh, r)
    equal("energy_balance", q+sheet_pv[days, slots]/6+d+h-sheet_load[days, slots]/6-c-w, 0)
    equal("soc_recurrence", e1-e0-.9*c+d/.9, 0)
    equal("soc_continuity", e1[:-1], e0[1:])
    checks["physical_bounds"] = bool(min(q0.min(), q.min(), c.min(), d.min(), h.min(), w.min()) >= -1e-7 and max(c.max(), d.max()) <= 5000/6+1e-7 and min(e0.min(), e1.min()) >= 1200-1e-7 and max(e0.max(), e1.max()) <= 10800+1e-7)
    checks["charge_discharge_exclusive"] = not bool(np.any((c>1e-7)&(d>1e-7)))
    checks["emergency_does_not_charge"] = not bool(np.any((h>1e-7)&(c>1e-7)))
    signs = np.where(frame.settlement == "A", 1., -1.)
    checks["settlement_labels"] = bool(frame.settlement.isin(["A", "B"]).all() and frame.settlement.nunique() == 1)
    components = {"base_cost_yuan": p*q0, "up_cost_yuan": 1.5*p*u,
                  "down_cost_yuan": .5*p*r*signs, "emergency_cost_yuan": 5*p*h}
    for name, values in components.items():
        equal(name, frame[name], values)
    total = sum(components.values())
    equal("total_cost_yuan", frame.total_cost_yuan, total)
    checks["one_confirmation_per_slot"] = (
        bool(np.isin(frame.confirmation_count, [0, 1]).all())
        if "confirmation_count" in frame else bool(np.max(np.abs(q-q0)) <= 1e-7)
    )
    checks["no_pre0600_adjustments"] = bool(np.max(np.abs((q-q0)[slots<35])) <= 1e-7)
    value = {"question": question, "ledger": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
             "passed": all(checks.values()), "checks": checks, "max_absolute_residuals": residuals,
             "days": 334, "rows": len(frame), "cash_total_yuan": float(total.sum()),
             "emergency_kwh": float(h.sum()), "end_soc_kwh": float(e1[-1]),
             "verification": "Independent attachment/transaction reconstruction; no optimizer invocation"}
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--question", choices=["Q3", "Q4"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Audit output is immutable")
    result = audit(args.ledger, args.question)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
