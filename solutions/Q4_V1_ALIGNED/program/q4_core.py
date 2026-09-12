"""Q4 adapter to the actual causal Q2 V3 ONLINE-RISK-SP implementation."""
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
VERSION = Path(__file__).resolve().parents[1]
Q2_PROGRAM = ROOT / "solutions/Q2_V3_CAUSAL_FORECAST/program"
sys.path.insert(0, str(Q2_PROGRAM))
import q2_model as model
import run_q2_v3 as online
from q2_forecasts import build_forecast_bundle


class MidnightPolicy:
    """Own candidate history per policy trajectory; planning sees no future prices."""

    def __init__(self, data, load_pred, pv_pred):
        self.data, self.load_pred, self.pv_pred = data, load_pred, pv_pred
        self.candidates = online.candidate_grid()
        self.histories = {c["candidate_id"]: [] for c in self.candidates}
        self.pending = []

    def plan(self, day, planned_e0, price_forecast):
        self.pending = online.release_mature_scores(self.pending, self.histories, day)
        scores = {key: float(np.mean(v[-online.WINDOW_DAYS:]))
                  for key, v in self.histories.items() if v}
        selected = min(scores, key=scores.get) if scores else online.DEFAULT_CANDIDATE
        plans, diagnostics = {}, {}
        for candidate in self.candidates:
            load_sc, pv_sc, weights = online._recency_scenarios(
                self.data, self.load_pred, self.pv_pred, day,
                online.SCENARIO_COUNT, online.SCENARIO_WINDOW, candidate["gamma"])
            grid, diag = model.two_stage_plan(
                price_forecast.values, load_sc, pv_sc, weights, planned_e0,
                terminal="value", terminal_lambda=online.TERMINAL_LAMBDA,
                cvar_beta=candidate["tau"] or 0., cvar_weight=candidate["rho"])
            plans[candidate["candidate_id"]] = grid
            diagnostics[candidate["candidate_id"]] = diag
        return selected, plans, {"scores": scores, "solver": diagnostics}

    def settle_candidate_scores(self, day, plans, executed_e0, actual_prices):
        scores = {}
        for key, grid in plans.items():
            result = model.settle_causally(grid, self.data.load[day], self.data.pv[day], executed_e0)
            scores[key] = float(actual_prices @ (grid + 5 * result["emergency"]))
        self.pending.append((day, scores))


def interval_ledger(data, day, q0, qfinal, settled, forecast, planned_e0,
                    executed_e0, actual_prices, selected_id, settlement="A"):
    if settlement not in ("A", "B"):
        raise ValueError("settlement must be A or B")
    up, down = np.maximum(qfinal - q0, 0), np.maximum(q0 - qfinal, 0)
    start = data.dates[day] + pd.to_timedelta((np.arange(144) + 1) * 10, unit="min")
    frame = pd.DataFrame({
        "plan_day": data.dates[day].date().isoformat(), "time_index": np.arange(144),
        "issue_time": data.dates[day].isoformat(), "interval_start": start,
        "interval_end": start + pd.Timedelta(minutes=10),
        "price_source_completed_at": forecast.source_completed_at,
        "price_model_id": forecast.model_id, "selected_candidate": selected_id,
        "forecast_model_id": "Q2V2-SW2-REC5", "time_mapping": "A",
        "battery_interpretation": "A", "settlement_rule": settlement,
        "residual_history_cutoff": data.dates[day].isoformat(),
        "planned_initial_energy_kwh": planned_e0,
        "executed_initial_energy_kwh": executed_e0,
        "planned_initial_source": "previous_confirmed_final_slot_and_issued_load_pv_forecast",
        "load_actual_kw": data.load[day], "pv_actual_kw": data.pv[day],
        "planned_grid_kwh": q0, "final_grid_kwh": qfinal,
        "up_kwh": up, "down_kwh": down,
        "charge_kwh": settled["c"], "discharge_kwh": settled["d"],
        "emergency_kwh": settled["emergency"], "unused_supply_kwh": settled["spill"],
        "actual_soc_before_kwh": settled["soc"][:-1],
        "actual_soc_after_kwh": settled["soc"][1:],
        "price_forecast_yuan_per_kwh": forecast.values,
        "price_actual_yuan_per_kwh": actual_prices,
        "base_cost_yuan": actual_prices * q0,
        "up_cost_yuan": 1.5 * actual_prices * up,
        "down_cost_yuan": (0.5 if settlement == "A" else -0.5) * actual_prices * down,
        "emergency_cost_yuan": 5 * actual_prices * settled["emergency"],
    })
    frame["ordinary_cost_yuan"] = frame.base_cost_yuan + frame.up_cost_yuan + frame.down_cost_yuan
    frame["cash_cost_yuan"] = frame.ordinary_cost_yuan + frame.emergency_cost_yuan
    validate_ledger(frame)
    return frame


def validate_ledger(frame, tol=1e-6):
    numeric = frame.select_dtypes(include=[np.number])
    if not np.isfinite(numeric.to_numpy()).all():
        raise AssertionError("nonfinite ledger")
    if frame.duplicated(["plan_day", "time_index"]).any():
        raise AssertionError("duplicate delivery")
    if not frame.groupby("plan_day").time_index.apply(lambda v: sorted(v) == list(range(144))).all():
        raise AssertionError("incomplete delivery day")
    balance = (frame.final_grid_kwh + frame.pv_actual_kw / 6 + frame.discharge_kwh
               + frame.emergency_kwh - frame.load_actual_kw / 6 - frame.charge_kwh - frame.unused_supply_kwh)
    soc = frame.actual_soc_before_kwh + .9 * frame.charge_kwh - frame.discharge_kwh / .9
    errors = [np.max(abs(balance)), np.max(abs(soc - frame.actual_soc_after_kwh)),
              np.max(abs(frame.final_grid_kwh - frame.planned_grid_kwh - frame.up_kwh + frame.down_kwh))]
    p = frame.price_actual_yuan_per_kwh
    sign = np.where(frame.settlement_rule == "A", .5, -.5)
    errors.extend([np.max(abs(frame.base_cost_yuan - p * frame.planned_grid_kwh)),
                   np.max(abs(frame.up_cost_yuan - 1.5 * p * frame.up_kwh)),
                   np.max(abs(frame.down_cost_yuan - sign * p * frame.down_kwh)),
                   np.max(abs(frame.emergency_cost_yuan - 5 * p * frame.emergency_kwh)),
                   np.max(abs(frame.ordinary_cost_yuan - frame.base_cost_yuan - frame.up_cost_yuan - frame.down_cost_yuan)),
                   np.max(abs(frame.cash_cost_yuan - frame.ordinary_cost_yuan - frame.emergency_cost_yuan))])
    energy = frame[["actual_soc_before_kwh", "actual_soc_after_kwh"]].to_numpy()
    nonnegative = frame[["planned_grid_kwh", "final_grid_kwh", "up_kwh", "down_kwh",
                         "charge_kwh", "discharge_kwh", "emergency_kwh", "unused_supply_kwh"]]
    if max(errors) > tol or energy.min() < 1200-tol or energy.max() > 10800+tol:
        raise AssertionError("physical or cash ledger mismatch")
    if nonnegative.to_numpy().min() < -tol or frame[["charge_kwh", "discharge_kwh"]].to_numpy().max() > 5000/6+tol:
        raise AssertionError("power/nonnegativity violation")
    if (np.minimum(frame.charge_kwh, frame.discharge_kwh) > tol).any():
        raise AssertionError("simultaneous charging and discharging")
    ordered = frame.sort_values(["plan_day", "time_index"])
    if len(ordered) > 1 and np.max(abs(ordered.actual_soc_before_kwh.to_numpy()[1:] - ordered.actual_soc_after_kwh.to_numpy()[:-1])) > tol:
        raise AssertionError("SOC discontinuity")
    if (pd.to_datetime(frame.price_source_completed_at) > pd.to_datetime(frame.issue_time)).any():
        raise AssertionError("price leakage")
    return {"passed": True, "intervals": len(frame), "max_residual": float(max(errors))}


def summarize(frame):
    validate_ledger(frame)
    daily = frame.groupby("plan_day").cash_cost_yuan.sum()
    end = float(frame.iloc[-1].actual_soc_after_kwh)
    return {"cash_cost_yuan": float(frame.cash_cost_yuan.sum()),
            "ordinary_cost_yuan": float(frame.ordinary_cost_yuan.sum()),
            "emergency_cost_yuan": float(frame.emergency_cost_yuan.sum()),
            "emergency_kwh": float(frame.emergency_kwh.sum()),
            "unused_supply_kwh": float(frame.unused_supply_kwh.sum()),
            "end_soc_kwh": end,
            "asset_adjusted_cost_yuan": float(frame.cash_cost_yuan.sum() + .4684*(6000-end)),
            "daily_cvar95_yuan": float(daily[daily >= daily.quantile(.95)].mean()),
            "days": len(daily), "review_status": "NOT_REVIEWED_PROVISIONAL"}
