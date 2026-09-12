"""Report paired cash, inventory and uncertainty from existing ledger files."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def read_daily(path):
    frame = pd.read_csv(path)
    if "cash_cost_yuan" in frame:
        cash = frame.cash_cost_yuan
    elif "total_cost_yuan" in frame:
        cash = frame.total_cost_yuan
    else:
        cash = frame.plan_cost_yuan + frame.emergency_cost_yuan
    frame["cash"] = cash
    frame["soc_end"] = frame["soc_after_kwh"] if "soc_after_kwh" in frame else frame.actual_soc_after_kwh
    frame["soc_start"] = frame["soc_before_kwh"] if "soc_before_kwh" in frame else frame.actual_soc_before_kwh
    frame["plan_day"] = pd.to_datetime(frame.plan_day)
    frame = frame.sort_values(["plan_day", "time_index"])
    if frame.duplicated(["plan_day", "time_index"]).any():
        raise ValueError("duplicate transactions")
    return frame.groupby("plan_day").agg(cash=("cash", "sum"), emergency=("emergency_kwh", "sum"),
        soc_end=("soc_end", "last"), soc_start=("soc_start", "first"), slots=("time_index", "count"))


def cvar(values):
    ordered = np.sort(values)
    return float(ordered[-max(1, int(np.ceil(.05*len(ordered)))):].mean())


def summarize(frame, seed=20260913):
    saving = frame.cash_baseline.to_numpy()-frame.cash_candidate.to_numpy()
    rng = np.random.default_rng(seed)
    intervals = {}
    for block in (3, 7, 14):
        starts = rng.integers(0, len(saving)-block+1, size=(2000, int(np.ceil(len(saving)/block))))
        indices = (starts[:, :, None]+np.arange(block)).reshape(2000, -1)[:, :len(saving)]
        means = saving[indices].mean(axis=1)
        intervals[str(block)] = np.quantile(means, [.025, .975]).tolist()
    b0, c0 = float(frame.soc_start_baseline.iloc[0]), float(frame.soc_start_candidate.iloc[0])
    b1, c1 = float(frame.soc_end_baseline.iloc[-1]), float(frame.soc_end_candidate.iloc[-1])
    return {"days": len(frame), "baseline_cash_yuan": float(frame.cash_baseline.sum()),
        "candidate_cash_yuan": float(frame.cash_candidate.sum()), "cash_saving_yuan": float(saving.sum()),
        "inventory_adjusted_saving_yuan": float(saving.sum()+.4684*((b0-b1)-(c0-c1))),
        "baseline_initial_soc_kwh": b0, "candidate_initial_soc_kwh": c0,
        "baseline_end_soc_kwh": b1, "candidate_end_soc_kwh": c1,
        "baseline_emergency_kwh": float(frame.emergency_baseline.sum()),
        "candidate_emergency_kwh": float(frame.emergency_candidate.sum()),
        "baseline_daily_cvar95_yuan": cvar(frame.cash_baseline.to_numpy()),
        "candidate_daily_cvar95_yuan": cvar(frame.cash_candidate.to_numpy()),
        "bootstrap_mean_daily_cash_saving_ci95_yuan": intervals}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("Comparison version already exists")
    b, c = read_daily(args.baseline), read_daily(args.candidate)
    dates = pd.date_range("2025-02-01", "2025-12-31")
    for frame in (b, c):
        if not dates.isin(frame.index).all() or not (frame.loc[dates, "slots"] == 144).all():
            raise ValueError("Comparison requires all 334 complete plan days")
    paired = b.loc[dates].join(c.loc[dates], lsuffix="_baseline", rsuffix="_candidate")
    paired["cash_saving_yuan"] = paired.cash_baseline-paired.cash_candidate
    result = {"selection_allowed": False, "model_rerun": False,
        "source_hashes": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.baseline, args.candidate)},
        "all_334_days": summarize(paired), "development_feb_jun": summarize(paired.loc[:"2025-06-30"]),
        "retrospective_jul_dec": summarize(paired.loc["2025-07-01":]),
        "limitations": ["Previously observed audit period; do not use for iterative parameter selection.",
            "Bootstrap intervals are descriptive and do not remove development selection bias.",
            "Inventory adjustment at frozen 0.4684 yuan/kWh is comparison-only, not cash revenue.",
            "Policies may differ in both forecasts and adjustment; this comparison alone does not isolate either effect."]}
    args.output_dir.mkdir(parents=True)
    paired.to_csv(args.output_dir / "paired_daily.csv", index_label="plan_day")
    monthly = {month: summarize(part) for month, part in paired.groupby(paired.index.strftime("%Y-%m"))}
    pd.DataFrame(monthly).T.to_csv(args.output_dir / "paired_monthly.csv", index_label="month")
    (args.output_dir / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["all_334_days"], indent=2))


if __name__ == "__main__":
    main()
