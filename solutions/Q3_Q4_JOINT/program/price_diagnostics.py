"""Describe the frozen lag-seven price model; no tuning or optimizer calls."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("Diagnostic output is immutable")
    source = ROOT / "data/附件4.xlsx"
    prior_source = ROOT / "data/附件1.xlsx"
    frame = pd.read_excel(source)
    dates = pd.DatetimeIndex(pd.to_datetime(frame.iloc[:, 0]))
    actual = frame.iloc[:, 1:].to_numpy(float)
    prior = pd.read_excel(prior_source).iloc[:, 1].to_numpy(float)
    days = np.arange(31, 365)
    predictions = {"frozen_lag7": actual[days-7], "fixed_attachment1_diagnostic": np.tile(prior, (334, 1))}
    rows = []
    for model, prediction in predictions.items():
        errors = prediction-actual[days]
        for offset, day in enumerate(days):
            rows.append({"plan_day": dates[day].date().isoformat(), "model": model,
                "mae_yuan_per_kwh": float(np.mean(np.abs(errors[offset]))),
                "mse_yuan2_per_kwh2": float(np.mean(errors[offset]**2)),
                "bias_yuan_per_kwh": float(errors[offset].mean())})
    daily = pd.DataFrame(rows)
    summaries = []
    for period, mask in [("all_334_days", np.ones(len(daily), bool)),
                         ("development_feb_jun", daily.plan_day <= "2025-06-30"),
                         ("retrospective_jul_dec", daily.plan_day >= "2025-07-01")]:
        for model, part in daily.loc[mask].groupby("model"):
            summaries.append({"period": period, "model": model, "days": len(part),
                "intervals": len(part)*144, "mae_yuan_per_kwh": float(part.mae_yuan_per_kwh.mean()),
                "rmse_yuan_per_kwh": float(np.sqrt(part.mse_yuan2_per_kwh2.mean())),
                "bias_yuan_per_kwh": float(part.bias_yuan_per_kwh.mean())})
    args.output_dir.mkdir(parents=True)
    daily.to_csv(args.output_dir / "price_error_daily.csv", index=False)
    pd.DataFrame(summaries).to_csv(args.output_dir / "price_error_summary.csv", index=False)
    metadata = {"prediction_time": "midnight", "intervals_per_model": 48096,
        "model_rerun": False, "selection_allowed": False,
        "source_hashes": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, prior_source)},
        "limitations": ["Prediction error does not establish dispatch savings.", "Fixed-price comparator is diagnostic only; the frozen Q4 policy remains lag7.", "July-December is retrospective, not an untouched validation set."]}
    (args.output_dir / "diagnostic_manifest.json").write_text(json.dumps(metadata, indent=2)+"\n")
    print(pd.DataFrame(summaries).to_string(index=False))


if __name__ == "__main__":
    main()
