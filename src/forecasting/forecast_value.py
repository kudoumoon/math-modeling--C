"""Forecast-only ablations under a fixed causal dispatch proxy, not contest results."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .data import daily_to_long, load_problem_data
from .drift import adapt_daily_forecasts
from .economic_backtest import _causal_residual_quantiles, _simulate
from .rolling_backtest import _bootstrap_mean


def _matrix(frame: pd.DataFrame, dates: pd.DatetimeIndex, pv: bool = False) -> pd.DataFrame:
    rows = []
    for date in dates:
        part = frame[frame.issue_time == date].sort_values("target_time")
        prediction = part.prediction.to_numpy(float)
        if pv:
            prediction = np.repeat(prediction, 6)
        if prediction.shape != (144,) or not np.isfinite(prediction).all():
            raise ValueError(f"incomplete prediction grid at {date}")
        rows.append(prediction)
    return pd.DataFrame(rows, index=dates)


def run_forecast_value(root: Path, run_dir: Path, cfg: dict) -> dict:
    data = load_problem_data(root)
    candidates = pd.read_csv(run_dir / "predictions/candidate_predictions.csv",
                             parse_dates=["issue_time", "target_time"])
    names = json.loads((run_dir / "artifacts/selected_models.json").read_text())
    dates = pd.date_range(cfg["first_forecast_date"], cfg["last_forecast_date"])
    baseline_names = {"load_10min": "seasonal_naive", "pv_hourly": "raw_official",
                      "price_10min": "seasonal_naive"}
    baseline, selected, adapted = {}, {}, {}
    adaptation_rows = []
    for target in baseline_names:
        part = candidates[candidates.target_name == target]
        naive = part[part.model == baseline_names[target]]
        chosen = part[part.model == names[target]]
        baseline[target] = _matrix(naive, dates, pv=target == "pv_hourly")
        selected[target] = _matrix(chosen, dates, pv=target == "pv_hourly")
        if target != "pv_hourly":
            actual = data.load if target == "load_10min" else data.price
            actual_long = daily_to_long(actual, "actual").rename(columns={"interval_start": "target_time"})
            online = adapt_daily_forecasts(chosen, actual_long)
            output = online.copy()
            output["prediction"] = output["adaptive_prediction"]
            adapted[target] = _matrix(output, dates)
            for split, group in online.groupby("split"):
                for label, col in (("static", "prediction"), ("adaptive", "adaptive_prediction")):
                    error = group[col] - group["actual"]
                    adaptation_rows.append(dict(target_name=target, split=split, variant=label,
                                                n=len(group), mae=error.abs().mean(),
                                                rmse=np.sqrt((error ** 2).mean()), bias=error.mean()))
            trace_cols = ["target_name", "model", "issue_time", "target_time", "prediction",
                          "online_correction", "drift_score", "adaptive_prediction"]
            online[trace_cols].to_csv(run_dir / "predictions" / f"{target}_adaptation.csv", index=False)
        else:
            adapted[target] = selected[target]
    variants = {"naive": baseline, "selected": selected, "adaptive": adapted}
    for target, label in (("load_10min", "load_only"), ("pv_hourly", "pv_only"), ("price_10min", "price_only")):
        variants[label] = dict(baseline, **{target: selected[target]})
    fixed = pd.read_excel(root / "data/附件1.xlsx")["电价"].to_numpy(float)
    fixed_price = pd.DataFrame(np.tile(fixed, (len(dates), 1)), index=dates)
    actual_net = data.load.loc[dates] - data.pv_actual.loc[dates]
    records = []
    for scenario in ("fixed_price_proxy", "variable_price_proxy"):
        for variant, forecasts in variants.items():
            if scenario == "fixed_price_proxy" and variant == "price_only":
                continue
            net = forecasts["load_10min"] - forecasts["pv_hourly"]
            margin = _causal_residual_quantiles(net, actual_net, alpha=0.70)
            decision = fixed_price if scenario == "fixed_price_proxy" else forecasts["price_10min"]
            settlement = fixed_price if scenario == "fixed_price_proxy" else data.price.loc[dates]
            result = _simulate(dates, net, margin, decision, settlement, data.load, data.pv_actual)
            result["scenario"] = scenario
            result["variant"] = variant
            result["split"] = np.where(result.date <= pd.Timestamp(cfg["development_end"]), "development", "audit")
            records.append(result)
    daily = pd.concat(records, ignore_index=True)
    summary_rows = []
    for (scenario, variant, split), part in daily.groupby(["scenario", "variant", "split"]):
        tail = part.cash_cost[part.cash_cost >= part.cash_cost.quantile(0.95)]
        summary_rows.append(dict(scenario=scenario, variant=variant, split=split, days=len(part),
                                 cash_cost=part.cash_cost.sum(), emergency_kwh=part.emergency_kwh.sum(),
                                 emergency_cost=part.emergency_cost.sum(), surplus_kwh=part.surplus_kwh.sum(),
                                 daily_cost_p95=part.cash_cost.quantile(0.95), daily_cost_cvar95=tail.mean(),
                                 final_energy_kwh=part.end_energy_kwh.iloc[-1]))
    summary = pd.DataFrame(summary_rows)
    comparisons = []
    for (scenario, split), part in daily.groupby(["scenario", "split"]):
        table = part.pivot(index="date", columns="variant", values="cash_cost")
        for variant in table.columns.difference(["naive"]):
            gain = table.naive - table[variant]
            for block in (3, 7, 14):
                comparisons.append(dict(scenario=scenario, split=split, variant=variant,
                                        baseline="naive", block_days=block, cash_savings=gain.sum(),
                                        **_bootstrap_mean(gain.to_numpy(), block=block, seed=cfg["seed"])))
    # Freeze the deployable choice using development cash only, with naive as an explicit fallback.
    selections = {}
    for scenario, part in summary[summary.split == "development"].groupby("scenario"):
        options = part[part.variant.isin(["naive", "selected", "adaptive"])]
        selections[scenario] = options.loc[options.cash_cost.idxmin(), "variant"]
    daily.to_csv(run_dir / "reports/forecast_value_daily.csv", index=False)
    summary.to_csv(run_dir / "reports/forecast_value_summary.csv", index=False)
    pd.DataFrame(comparisons).to_csv(run_dir / "reports/forecast_value_bootstrap.csv", index=False)
    pd.DataFrame(adaptation_rows).to_csv(run_dir / "reports/adaptation_ablation.csv", index=False)
    report = {"development_selections": selections, "alpha": 0.70, "initial_energy_kwh": 6000,
              "start_date": str(dates[0]), "end_date": str(dates[-1]),
              "interpretation": "Fixed causal dispatch proxy, not final Q1-Q4 results. February start; no January warmup. "
              "Forecast channels and their causal residual margins vary; controller, prices for settlement and initial state are shared. "
              "Audit is retrospective; choices use development cash only. Ending assets are disclosed, not monetized."}
    (run_dir / "reports/forecast_value.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
