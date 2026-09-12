"""Compare static, adaptive, and adaptive-economic forecasting policies."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .adaptive import AdaptiveConfig, adapt_daily_forecasts
from .data import load_problem_data, daily_to_long
from .economic import execute_day, plan_day


ALPHAS = (0.65, 0.70, 0.75, 0.80, 0.85, 0.90)


def _actual_long(matrix: pd.DataFrame) -> pd.DataFrame:
    return daily_to_long(matrix, "actual")[["interval_start", "actual"]].rename(
        columns={"interval_start": "target_time"}
    )


def _daily_prediction_matrix(predictions: pd.DataFrame, target: str, actual: pd.DataFrame):
    frame = predictions[predictions["target_name"] == target].copy()
    adapted = adapt_daily_forecasts(frame, _actual_long(actual), AdaptiveConfig())
    base_rows = []
    online_rows = []
    for issue, group in adapted.groupby("issue_time"):
        group = group.sort_values("target_time")
        if len(group) != 144:
            raise ValueError(f"{issue}: expected 144 {target} intervals")
        base_rows.append(pd.Series(group["prediction"].to_numpy(), name=issue))
        online_rows.append(pd.Series(group["adaptive_prediction"].to_numpy(), name=issue))
    base = pd.DataFrame(base_rows)
    online = pd.DataFrame(online_rows)
    return adapted, base, online


def _pv_daily(predictions: pd.DataFrame) -> pd.DataFrame:
    pv = predictions[
        (predictions["target_name"] == "pv_hourly") & (predictions["issue_hour"] == 0)
    ].sort_values(["issue_time", "lead_hour"])
    rows = []
    for issue, group in pv.groupby("issue_time"):
        hourly = group.sort_values("lead_hour")["prediction"].to_numpy()
        if len(hourly) != 24:
            raise ValueError(f"{issue}: expected 24 PV forecast hours")
        rows.append(pd.Series(np.repeat(hourly, 6), name=issue))
    return pd.DataFrame(rows)


def _causal_residual_quantiles(
    predicted_net: pd.DataFrame,
    actual_net: pd.DataFrame,
    alpha: float,
    window_days: int = 28,
) -> pd.DataFrame:
    residual = actual_net - predicted_net
    margin = np.zeros_like(residual.to_numpy())
    for i in range(len(residual)):
        for slot in range(residual.shape[1]):
            end = i - 1 if slot == 143 else i
            start = max(0, end - window_days)
            history = residual.iloc[start:end, slot].dropna()
            margin[i, slot] = history.quantile(alpha) if len(history) >= 7 else 0.0
    return pd.DataFrame(margin, index=predicted_net.index, columns=predicted_net.columns)


def _simulate(
    dates: pd.DatetimeIndex,
    net_forecast: pd.DataFrame,
    risk_margin: pd.DataFrame,
    decision_price: pd.DataFrame,
    settlement_price: pd.DataFrame,
    load_actual: pd.DataFrame,
    pv_actual: pd.DataFrame,
) -> pd.DataFrame:
    energy = 6000.0
    rows = []
    for date in dates:
        q = plan_day(
            net_forecast.loc[date].to_numpy() + risk_margin.loc[date].to_numpy(),
            decision_price.loc[date].to_numpy(),
            energy,
        )
        result = execute_day(
            q,
            load_actual.loc[date].to_numpy(),
            pv_actual.loc[date].to_numpy(),
            settlement_price.loc[date].to_numpy(),
            energy,
        )
        rows.append({
            "date": date,
            "normal_cost": result.normal_cost,
            "emergency_cost": result.emergency_cost,
            "cash_cost": result.cash_cost,
            "emergency_kwh": result.emergency.sum(),
            "surplus_kwh": result.surplus.sum(),
            "end_energy_kwh": result.end_energy,
        })
        energy = result.end_energy
    return pd.DataFrame(rows)


def run_economic_backtest(root: str | Path = ".") -> dict:
    root = Path(root)
    data = load_problem_data(root)
    predictions = pd.read_csv(root / "predictions" / "causal_forecasts.csv")
    for col in ("issue_time", "target_time", "train_end"):
        predictions[col] = pd.to_datetime(predictions[col])
    dates = pd.date_range("2025-02-01", "2025-12-31", freq="D")

    load_detail, load_base_wide, load_online_wide = _daily_prediction_matrix(
        predictions, "load_10min", data.load
    )
    _, price_base_wide, price_online_wide = _daily_prediction_matrix(
        predictions, "price_10min", data.price
    )
    load_base = pd.DataFrame(load_base_wide.to_numpy(), index=dates)
    load_online = pd.DataFrame(load_online_wide.to_numpy(), index=dates)
    price_base = pd.DataFrame(price_base_wide.to_numpy(), index=dates)
    price_online = pd.DataFrame(price_online_wide.to_numpy(), index=dates)
    pv_forecast = _pv_daily(predictions)
    pv_forecast.index = pd.DatetimeIndex(pv_forecast.index).normalize()
    pv_forecast = pv_forecast.loc[dates]
    load_actual = data.load.loc[dates]
    pv_actual = data.pv_actual.loc[dates]
    price_actual = data.price.loc[dates]
    actual_net = load_actual - pv_actual
    base_net = load_base - pv_forecast
    online_net = load_online - pv_forecast

    fixed_price = pd.read_excel(root / "data" / "附件1.xlsx")["电价"].to_numpy(float)
    fixed_price = pd.DataFrame(np.tile(fixed_price, (len(dates), 1)), index=dates)
    cases = {
        "q3_fixed_price": (fixed_price, fixed_price),
        "q4_variable_price": (price_online, price_actual),
    }
    development = dates[dates <= pd.Timestamp("2025-06-30")]
    outputs = []
    selections = {}
    for case, (decision_price, settlement_price) in cases.items():
        alpha_costs = {}
        for alpha in ALPHAS:
            margin = _causal_residual_quantiles(online_net, actual_net, alpha)
            result = _simulate(
                development, online_net, margin, decision_price, settlement_price,
                load_actual, pv_actual,
            )
            alpha_costs[alpha] = result["cash_cost"].sum()
        selected_alpha = min(alpha_costs, key=alpha_costs.get)
        selections[case] = {"alpha": selected_alpha, "development_costs": alpha_costs}
        policies = {
            "static_alpha70": (base_net, 0.70, price_base if case == "q4_variable_price" else decision_price),
            "adaptive_alpha70": (online_net, 0.70, decision_price),
            "adaptive_economic": (online_net, selected_alpha, decision_price),
        }
        for policy, (net, alpha, policy_price) in policies.items():
            margin = _causal_residual_quantiles(net, actual_net, alpha)
            result = _simulate(
                dates, net, margin, policy_price, settlement_price, load_actual, pv_actual
            )
            result["case"] = case
            result["policy"] = policy
            result["alpha"] = alpha
            result["split"] = np.where(
                result["date"] <= pd.Timestamp("2025-06-30"), "development", "audit"
            )
            outputs.append(result)
    daily = pd.concat(outputs, ignore_index=True)
    summary = daily.groupby(["case", "policy", "alpha", "split"], as_index=False).agg(
        days=("date", "size"),
        cash_cost=("cash_cost", "sum"),
        normal_cost=("normal_cost", "sum"),
        emergency_cost=("emergency_cost", "sum"),
        emergency_kwh=("emergency_kwh", "sum"),
        surplus_kwh=("surplus_kwh", "sum"),
        final_energy_kwh=("end_energy_kwh", "last"),
    )
    report_dir = root / "reports"
    report_dir.mkdir(exist_ok=True)
    daily.to_csv(report_dir / "economic_backtest_daily.csv", index=False)
    summary.to_csv(report_dir / "economic_backtest_summary.csv", index=False)
    (root / "artifacts" / "economic_policy.json").write_text(
        json.dumps(selections, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"selections": selections, "summary": summary.to_dict("records")}


if __name__ == "__main__":
    print(json.dumps(run_economic_backtest(), ensure_ascii=False, indent=2, default=str))
