"""Non-anticipative Q3/Q4 rolling contract backtest and evidence tables."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .data import SLOTS_PER_DAY, daily_to_long, load_problem_data
from .drift import DriftConfig, adapt_daily_forecasts
from .economic import DT_HOURS, E_MAX, E_MIN, ETA_C, ETA_D, P_MAX_ENERGY, plan_day, project_interval_energy


ISSUE_HOURS = (6, 12, 18)
DATES = pd.date_range("2025-02-01", "2025-12-31", freq="D")


def _actual_long(matrix: pd.DataFrame) -> pd.DataFrame:
    return daily_to_long(matrix, "actual")[["interval_start", "actual"]].rename(
        columns={"interval_start": "target_time"}
    )


def _daily_predictions(predictions: pd.DataFrame, target: str, actual: pd.DataFrame):
    frame = predictions[predictions["target_name"] == target].copy()
    adapted = adapt_daily_forecasts(frame, _actual_long(actual), DriftConfig())
    base = {}
    online = {}
    for issue, group in adapted.groupby("issue_time"):
        group = group.sort_values("target_time")
        if len(group) != SLOTS_PER_DAY:
            raise ValueError(f"{issue}: expected 144 {target} forecasts")
        date = pd.Timestamp(issue).normalize()
        base[date] = group["prediction"].to_numpy(float)
        online[date] = group["adaptive_prediction"].to_numpy(float)
    return adapted, pd.DataFrame.from_dict(base, orient="index"), pd.DataFrame.from_dict(online, orient="index")


def _pv_issue_lookup(predictions: pd.DataFrame) -> dict[tuple[pd.Timestamp, pd.Timestamp], float]:
    pv = predictions[predictions["target_name"] == "pv_hourly"].copy()
    pv["issue_time"] = pd.to_datetime(pv["issue_time"])
    lookup: dict[tuple[pd.Timestamp, pd.Timestamp], float] = {}
    for issue, group in pv.groupby("issue_time"):
        for row in group.itertuples(index=False):
            start = issue + pd.Timedelta(minutes=10) + pd.Timedelta(hours=int(row.lead_hour) - 1)
            for j in range(6):
                lookup[(issue, start + j * pd.Timedelta(minutes=10))] = float(row.prediction)
    return lookup


def _issue_pv_day(
    date: pd.Timestamp,
    issue_hour: int,
    lookup: dict[tuple[pd.Timestamp, pd.Timestamp], float],
) -> np.ndarray:
    issue = date + pd.Timedelta(hours=issue_hour)
    values = np.full(SLOTS_PER_DAY, np.nan)
    for slot in range(SLOTS_PER_DAY):
        start = date + pd.Timedelta(minutes=10 * (slot + 1))
        values[slot] = lookup.get((issue, start), np.nan)
    return values


def _lag7_pv(data, date: pd.Timestamp) -> np.ndarray:
    return data.pv_actual.loc[date - pd.Timedelta(days=7)].to_numpy(float)


def _same_day_load_update(
    date: pd.Timestamp,
    issue_hour: int,
    base_load: np.ndarray,
    actual_load: np.ndarray,
    weight: float = 0.75,
    lookback_intervals: int = 12,
) -> np.ndarray:
    times = date + pd.to_timedelta((np.arange(SLOTS_PER_DAY) + 1) * 10, unit="min")
    issue = date + pd.Timedelta(hours=issue_hour)
    complete = times + pd.Timedelta(minutes=10) <= issue
    residual = actual_load[complete] - base_load[complete]
    correction = float(np.mean(residual[-lookback_intervals:])) if len(residual) else 0.0
    future = (times > issue) & (times <= issue + pd.Timedelta(hours=6))
    updated = base_load.copy()
    updated[future] = np.clip(updated[future] + weight * correction, 0, None)
    return updated


def _execute_contract(
    q0: np.ndarray,
    q_final: np.ndarray,
    actual_load: np.ndarray,
    actual_pv: np.ndarray,
    settlement_price: np.ndarray,
    initial_energy: float,
) -> dict:
    energy = float(initial_energy)
    charge = np.zeros(SLOTS_PER_DAY)
    discharge = np.zeros(SLOTS_PER_DAY)
    emergency = np.zeros(SLOTS_PER_DAY)
    surplus = np.zeros(SLOTS_PER_DAY)
    for t in range(SLOTS_PER_DAY):
        if t == SLOTS_PER_DAY - 1:
            energy_before_final = energy
        available = q_final[t] + actual_pv[t] * DT_HOURS - actual_load[t] * DT_HOURS
        if available >= 0:
            charge[t] = min(available, P_MAX_ENERGY, max(0.0, (E_MAX - energy) / ETA_C))
            energy += ETA_C * charge[t]
            surplus[t] = available - charge[t]
        else:
            deficit = -available
            discharge[t] = min(deficit, P_MAX_ENERGY, max(0.0, ETA_D * (energy - E_MIN)))
            energy -= discharge[t] / ETA_D
            emergency[t] = deficit - discharge[t]
    increase = np.clip(q_final - q0, 0, None)
    decrease = np.clip(q0 - q_final, 0, None)
    normal_cost = float(np.dot(settlement_price, q0))
    adjustment_cost = float(np.dot(1.5 * settlement_price, increase) + np.dot(0.5 * settlement_price, decrease))
    emergency_cost = float(np.dot(5.0 * settlement_price, emergency))
    return {
        "normal_cost": normal_cost,
        "adjustment_cost": adjustment_cost,
        "emergency_cost": emergency_cost,
        "cash_cost": normal_cost + adjustment_cost + emergency_cost,
        "emergency_kwh": float(emergency.sum()),
        "surplus_kwh": float(surplus.sum()),
        "end_energy_kwh": float(energy),
        "energy_before_final": float(energy_before_final),
        "adjustment_up_kwh": float(increase.sum()),
        "adjustment_down_kwh": float(decrease.sum()),
    }


def _economic_gate(
    date: pd.Timestamp,
    row_index: int,
    block: np.ndarray,
    q0: np.ndarray,
    candidate: np.ndarray,
    net_pred: pd.DataFrame,
    residual: pd.DataFrame,
    decision_price: pd.DataFrame,
    min_history: int = 14,
) -> tuple[bool, float, float]:
    """Causal dispatch gate: apply an update only if its expected cash benefit is positive."""
    if row_index < min_history or not np.any(block):
        return False, 0.0, 0.0
    start = max(0, row_index - 56)
    hist = residual.iloc[start:row_index, block].dropna(how="any")
    if len(hist) < min_history:
        return False, 0.0, 0.0
    pred = net_pred.loc[date].to_numpy(float)[block]
    q_base = q0[block]
    q_new = candidate[block]
    prices = decision_price.loc[date].to_numpy(float)[block]
    actual_net_kwh = (pred[None, :] + hist.to_numpy(float)) * DT_HOURS
    base_emergency = np.maximum(actual_net_kwh - q_base[None, :], 0.0)
    new_emergency = np.maximum(actual_net_kwh - q_new[None, :], 0.0)
    avoided_emergency = np.sum(5.0 * prices[None, :] * (base_emergency - new_emergency), axis=1)
    increase = np.clip(q_new - q_base, 0.0, None)
    decrease = np.clip(q_base - q_new, 0.0, None)
    adjustment_fee = float(np.dot(1.5 * prices, increase) + np.dot(0.5 * prices, decrease))
    net_benefit = avoided_emergency - adjustment_fee
    expected = float(np.mean(net_benefit))
    downside = float(np.quantile(net_benefit, 0.25))
    return bool(expected > 0.0 and downside > 0.0), expected, downside


def _simulate_policy(
    data,
    date_index: pd.DatetimeIndex,
    load_forecast: pd.DataFrame,
    pv_forecast: dict[pd.Timestamp, np.ndarray],
    pv_updates: bool,
    price_forecast: pd.DataFrame,
    settlement_price: pd.DataFrame,
    alpha: float,
    use_adjustment: bool,
    pv_lookup: dict,
) -> pd.DataFrame:
    actual_net = data.load.loc[date_index] - data.pv_actual.loc[date_index]
    net_pred = pd.DataFrame(
        [load_forecast.loc[d].to_numpy() - pv_forecast[d] for d in date_index], index=date_index
    )
    # One-step causal residual quantiles; slot 143 excludes the not-yet-complete interval.
    residual = actual_net - net_pred
    margins = np.zeros_like(residual.to_numpy())
    for i, date in enumerate(date_index):
        for slot in range(SLOTS_PER_DAY):
            end = max(0, i - 1) if slot == 143 else i
            history = residual.iloc[max(0, end - 28):end, slot].dropna()
            margins[i, slot] = history.quantile(alpha) if len(history) >= 7 else 0.0
    margins = pd.DataFrame(margins, index=date_index)

    actual_energy = 6000.0
    estimated_energy = 6000.0
    rows = []
    for i, date in enumerate(date_index):
        q0 = plan_day(
            net_pred.loc[date].to_numpy() + margins.loc[date].to_numpy(),
            price_forecast.loc[date].to_numpy(),
            estimated_energy,
        )
        q_final = q0.copy()
        pending_net_forecast = net_pred.loc[date].iloc[-1]
        gate_passes = 0
        gate_expected_net = 0.0
        if use_adjustment:
            for issue_hour in ISSUE_HOURS:
                issue = date + pd.Timedelta(hours=issue_hour)
                new_pv = _issue_pv_day(date, issue_hour, pv_lookup)
                if not np.isfinite(new_pv).any():
                    continue
                updated_load = _same_day_load_update(
                    date, issue_hour, load_forecast.loc[date].to_numpy(), data.load.loc[date].to_numpy()
                )
                times = date + pd.to_timedelta((np.arange(SLOTS_PER_DAY) + 1) * 10, unit="min")
                block = (times > issue) & (times <= issue + pd.Timedelta(hours=6)) & np.isfinite(new_pv)
                if block[-1]:
                    pending_net_forecast = updated_load[-1] - new_pv[-1]
                delta = (updated_load - load_forecast.loc[date].to_numpy()) - (
                    new_pv - pv_forecast[date]
                )
                candidate = q_final.copy()
                candidate[block] = np.clip(q0[block] + delta[block] * DT_HOURS, 0, None)
                allowed, expected, _ = _economic_gate(
                    date, i, block, q0, candidate, net_pred, residual, price_forecast
                )
                if allowed:
                    q_final[block] = candidate[block]
                    gate_passes += 1
                    gate_expected_net += expected
        result = _execute_contract(
            q0, q_final, data.load.loc[date].to_numpy(), data.pv_actual.loc[date].to_numpy(),
            settlement_price.loc[date].to_numpy(), actual_energy,
        )
        result.update({"date": date, "alpha": alpha, "pv_updates": int(pv_updates), "adjustment": int(use_adjustment),
                       "gate_passes": gate_passes, "gate_expected_net": gate_expected_net,
                       "actual_initial_energy_kwh": actual_energy,
                       "estimated_initial_energy_kwh": estimated_energy})
        rows.append(result)
        estimated_energy = project_interval_energy(
            result["energy_before_final"], q_final[-1], pending_net_forecast
        )
        actual_energy = result["end_energy_kwh"]
    return pd.DataFrame(rows)


def _bootstrap_mean(values: np.ndarray, block: int = 7, n_boot: int = 2000, seed: int = 20260912):
    values = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    if len(values) == 0:
        return {"mean": np.nan, "lower_95": np.nan, "upper_95": np.nan}
    starts = np.arange(max(1, len(values) - block + 1))
    means = np.empty(n_boot)
    for b in range(n_boot):
        sample = []
        while len(sample) < len(values):
            start = int(rng.choice(starts))
            sample.extend(values[start:start + block])
        means[b] = np.mean(sample[:len(values)])
    return {
        "mean": float(np.mean(values)),
        "lower_95": float(np.quantile(means, 0.025)),
        "upper_95": float(np.quantile(means, 0.975)),
    }


def run_rolling_backtest(root: str | Path = ".") -> dict:
    root = Path(root)
    data = load_problem_data(root)
    predictions = pd.read_csv(root / "predictions" / "causal_forecasts.csv")
    for col in ("issue_time", "target_time", "train_end"):
        predictions[col] = pd.to_datetime(predictions[col])
    _, load_base, load_online = _daily_predictions(predictions, "load_10min", data.load)
    _, price_base, price_online = _daily_predictions(predictions, "price_10min", data.price)
    load_base = load_base.loc[DATES]; load_online = load_online.loc[DATES]
    price_base = price_base.loc[DATES]; price_online = price_online.loc[DATES]
    pv_lookup = _pv_issue_lookup(predictions)
    pv_official = {d: _issue_pv_day(d, 0, pv_lookup) for d in DATES}
    pv_lag7 = {d: _lag7_pv(data, d) for d in DATES}
    fixed_price_values = pd.read_excel(root / "data" / "附件1.xlsx")["电价"].to_numpy(float)
    fixed_price = pd.DataFrame(np.tile(fixed_price_values, (len(DATES), 1)), index=DATES)
    variable_price = data.price.loc[DATES]

    scenarios = {
        "q3": {"pv": pv_official, "decision": fixed_price, "settlement": fixed_price, "updates": True},
        "q4_2": {"pv": pv_lag7, "decision": price_online, "settlement": variable_price, "updates": False},
        "q4_3": {"pv": pv_official, "decision": price_online, "settlement": variable_price, "updates": True},
    }
    records = []
    for scenario, spec in scenarios.items():
        policies = [
            ("static", load_base, False, False),
            ("adaptive_no_updates", load_online, False, False),
        ]
        if spec["updates"]:
            policies.append(("adaptive_rolling", load_online, True, True))
        else:
            policies.append(("adaptive_rolling", load_online, False, False))
        for policy, load_fc, use_updates, use_adjustment in policies:
            result = _simulate_policy(
                data, DATES, load_fc, spec["pv"], use_updates, spec["decision"], spec["settlement"],
                alpha=0.70, use_adjustment=use_adjustment, pv_lookup=pv_lookup,
            )
            result["scenario"] = scenario; result["policy"] = policy
            result["split"] = np.where(result["date"] <= pd.Timestamp("2025-06-30"), "development", "audit")
            records.append(result)
    daily = pd.concat(records, ignore_index=True)
    summary = daily.groupby(["scenario", "policy", "split"], as_index=False).agg(
        days=("date", "size"), cash_cost=("cash_cost", "sum"), normal_cost=("normal_cost", "sum"),
        adjustment_cost=("adjustment_cost", "sum"), emergency_cost=("emergency_cost", "sum"),
        emergency_kwh=("emergency_kwh", "sum"), surplus_kwh=("surplus_kwh", "sum"),
        adjustment_up_kwh=("adjustment_up_kwh", "sum"), adjustment_down_kwh=("adjustment_down_kwh", "sum"),
        gate_passes=("gate_passes", "sum"), gate_expected_net=("gate_expected_net", "sum"),
        final_energy_kwh=("end_energy_kwh", "last"),
    )

    ablation_rows = []
    bootstrap_rows = []
    for scenario in scenarios:
        x = daily[(daily.scenario == scenario) & (daily.split == "audit")].pivot(
            index="date", columns="policy", values="cash_cost"
        )
        if "adaptive_rolling" not in x or "adaptive_no_updates" not in x:
            continue
        delta = x["adaptive_no_updates"] - x["adaptive_rolling"]
        ablation_rows.append({"scenario": scenario, "audit_days": len(delta), "rolling_minus_no_update_cost": -float(delta.sum()),
                              "rolling_savings_vs_no_update": float(delta.sum()), "positive_days": int((delta > 0).sum())})
        for block in (3, 7, 14):
            boot = _bootstrap_mean(delta.to_numpy(), block=block)
            bootstrap_rows.append({"scenario": scenario, "block_days": block, **boot})

    report_dir = root / "reports"; report_dir.mkdir(exist_ok=True)
    daily.to_csv(report_dir / "q3_q4_rolling_daily.csv", index=False)
    summary.to_csv(report_dir / "q3_q4_rolling_summary.csv", index=False)
    pd.DataFrame(ablation_rows).to_csv(report_dir / "q3_q4_information_ablation.csv", index=False)
    pd.DataFrame(bootstrap_rows).to_csv(report_dir / "q3_q4_block_bootstrap.csv", index=False)
    monthly = daily.assign(month=pd.to_datetime(daily["date"]).dt.to_period("M").astype(str)).groupby(
        ["scenario", "policy", "split", "month"], as_index=False
    ).agg(
        days=("date", "size"), cash_cost=("cash_cost", "sum"), normal_cost=("normal_cost", "sum"),
        adjustment_cost=("adjustment_cost", "sum"), emergency_cost=("emergency_cost", "sum"),
        emergency_kwh=("emergency_kwh", "sum"), surplus_kwh=("surplus_kwh", "sum"),
        gate_passes=("gate_passes", "sum"), gate_expected_net=("gate_expected_net", "sum"),
    )
    monthly.to_csv(report_dir / "q3_q4_monthly_decomposition.csv", index=False)
    report = {
        "scenarios": list(scenarios),
        "notes": [
            "Q3 uses 0/6/12/18 PV forecast releases and adjusts only future six-hour blocks.",
            "Q4-2 uses causal lag-7 PV because it inherits Q2 information; Q4-3 uses official PV releases.",
            "Actual prices are used only in the settlement ledger; price forecasts are used for Q4 decisions.",
            "All scenarios share the same causal load adapter, LP, feedback executor, initial energy, and alpha=0.70.",
            "Economic gate uses only prior completed days and requires positive mean and 25th-percentile avoided-emergency benefit after adjustment fees.",
        ],
        "summary": summary.to_dict("records"),
        "ablation": ablation_rows,
        "bootstrap": bootstrap_rows,
    }
    (report_dir / "q3_q4_rolling_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run_rolling_backtest(), ensure_ascii=False, indent=2, default=str))
