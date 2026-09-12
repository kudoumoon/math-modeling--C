"""Strict causal dynamic-price primitives for Q4.

The module has no silent model fallback.  The first seven days are an explicit
cold-start phase fixed by the model contract; all later price forecasts require
an observed seven-day lag and raise on missing history.
"""

from __future__ import annotations

import copy
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.optimize import linprog

PROGRAM_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Q2" / "program"))
sys.path.insert(0, str(ROOT / "Q3" / "v2" / "program"))

import q2_pipeline_v1 as core
import q2_v2_compatible as q2full


PRICE_FILE = ROOT / "附件" / "附件4.xlsx"
ALPHA = 0.60
RISK_WINDOW_DAYS = 60
MIN_RISK_DAYS = 7
COLD_START_DAYS = 7
RELEASE_STEP = {0: None, 6: 35, 12: 71, 18: 107}
TOL = 1e-8


@dataclass(frozen=True)
class PriceForecast:
    target_day: int
    issue_time: pd.Timestamp
    values: np.ndarray
    source_times: pd.DatetimeIndex
    current_actual_step: Optional[int]

    @property
    def max_source_time(self) -> pd.Timestamp:
        return pd.Timestamp(self.source_times.max())


@dataclass
class DayPlan:
    day: int
    decision_time: pd.Timestamp
    predicted_start_soc: float
    forecast: core.Forecast
    margin: np.ndarray
    price_forecast: PriceForecast
    q: np.ndarray
    allow_storage: bool
    max_lp_residual: float


@dataclass
class WarmContext:
    soc_midnight: float
    previous: DayPlan
    log: pd.DataFrame
    decisions: pd.DataFrame


def load_actual_prices(dataset: core.Dataset) -> np.ndarray:
    frame = pd.read_excel(PRICE_FILE, sheet_name=0, header=0)
    if frame.shape != (365, 145):
        raise AssertionError(f"附件4形状异常: {frame.shape}")
    dates = pd.DatetimeIndex(pd.to_datetime(frame.iloc[:, 0]))
    if not dates.equals(dataset.dates):
        raise AssertionError("附件4日期与附件2不一致")
    values = frame.iloc[:, 1:].apply(pd.to_numeric, errors="raise").to_numpy(float)
    if values.shape != (365, 144) or not np.isfinite(values).all() or (values <= 0).any():
        raise AssertionError("附件4价格必须为365x144有限正数")
    return values


def build_price_forecast(
    dataset: core.Dataset,
    actual_price: np.ndarray,
    target_day: int,
    issue_time: pd.Timestamp,
) -> PriceForecast:
    if target_day < COLD_START_DAYS:
        raise ValueError("价格预测历史不足：冷启动期不得调用lag7预测器")
    source_day = target_day - 7
    values = actual_price[source_day].copy()
    source_times = dataset.interval_starts(source_day)
    current_step: Optional[int] = None
    if dataset.dates[target_day].normalize() == pd.Timestamp(issue_time).normalize():
        release_hour = int(pd.Timestamp(issue_time).hour)
        if release_hour not in RELEASE_STEP:
            raise ValueError(f"不允许的价格发布时间: {issue_time}")
        current_step = RELEASE_STEP[release_hour]
        if current_step is not None:
            values[current_step] = actual_price[target_day, current_step]
            mutable = source_times.to_numpy(copy=True)
            mutable[current_step] = np.datetime64(issue_time)
            source_times = pd.DatetimeIndex(mutable)
    if pd.Timestamp(source_times.max()) > pd.Timestamp(issue_time):
        raise AssertionError("价格预测读取了决策时刻之后的实际价格")
    return PriceForecast(
        target_day=int(target_day),
        issue_time=pd.Timestamp(issue_time),
        values=values,
        source_times=source_times,
        current_actual_step=current_step,
    )


def causal_margin_60(
    dataset: core.Dataset,
    forecast_library: Dict[Tuple[str, str], Dict[int, core.Forecast]],
    combo: Tuple[str, str],
    issue_time: pd.Timestamp,
    alpha: float = ALPHA,
) -> Tuple[np.ndarray, Tuple[int, ...], Optional[pd.Timestamp]]:
    completed = [
        day for day in range(len(dataset.dates))
        if dataset.plan_end(day) <= issue_time
    ][-RISK_WINDOW_DAYS:]
    max_time = dataset.plan_end(completed[-1]) if completed else None
    if len(completed) < MIN_RISK_DAYS:
        return np.zeros(core.N_STEPS), tuple(completed), max_time
    residual = np.vstack([
        dataset.load_kwh[d] - dataset.pv_kwh[d] - forecast_library[combo][d].net_kwh
        for d in completed
    ])
    return np.maximum(np.quantile(residual, alpha, axis=0), 0.0), tuple(completed), max_time


def dynamic_terminal_curve(
    dataset: core.Dataset,
    actual_price: np.ndarray,
    forecast_library: Dict[Tuple[str, str], Dict[int, core.Forecast]],
    combo: Tuple[str, str],
    day: int,
    issue_time: pd.Timestamp,
) -> Dict[str, object]:
    if day + 1 >= len(dataset.dates):
        raise ValueError("最后一天没有附件内次日终端价值")
    future = q2full.make_forecast(dataset, day + 1, issue_time, combo)
    margin, residual_days, residual_max = causal_margin_60(
        dataset, forecast_library, combo, issue_time
    )
    price = build_price_forecast(dataset, actual_price, day + 1, issue_time)
    values = []
    for start_soc in q2full.R2_GRID:
        solved = q2full.solve_plan(
            future.net_kwh + margin,
            price.values,
            float(start_soc),
            "hard",
            hard_anchor=6000.0,
        )
        values.append(float(solved["cash"]))
    values_arr = np.asarray(values)
    slopes = np.diff(values_arr) / np.diff(q2full.R2_GRID)
    monotone = bool(np.max(slopes) <= 1e-7)
    convex = bool(np.min(np.diff(slopes)) >= -1e-7)
    if not monotone or not convex:
        raise AssertionError("动态价格终端价值曲线不满足单调凸性")
    return {
        "grid": q2full.R2_GRID.copy(),
        "values": values_arr,
        "slopes": slopes,
        "monotone": monotone,
        "convex": convex,
        "price_max_source_time": price.max_source_time,
        "residual_days": residual_days,
        "residual_max_time": residual_max,
    }


def predict_plan_start(soc_midnight: float, previous: DayPlan) -> float:
    if not previous.allow_storage:
        return float(soc_midnight)
    action = core.feedback_step(
        float(soc_midnight),
        float(previous.q[-1]),
        float(previous.forecast.load_kwh[-1]),
        float(previous.forecast.pv_kwh[-1]),
    )
    return float(action["soc_after_kwh"])


def make_dynamic_plan(
    dataset: core.Dataset,
    actual_price: np.ndarray,
    forecast_library: Dict[Tuple[str, str], Dict[int, core.Forecast]],
    combo: Tuple[str, str],
    day: int,
    predicted_start_soc: float,
) -> DayPlan:
    issue = dataset.dates[day]
    forecast = forecast_library[combo][day]
    margin, _, _ = causal_margin_60(dataset, forecast_library, combo, issue)
    price = build_price_forecast(dataset, actual_price, day, issue)
    if day == len(dataset.dates) - 1:
        solved = q2full.solve_plan(
            forecast.net_kwh + margin, price.values, predicted_start_soc,
            "hard", hard_anchor=6000.0,
        )
    else:
        curve = dynamic_terminal_curve(
            dataset, actual_price, forecast_library, combo, day, issue
        )
        solved = q2full.solve_plan(
            forecast.net_kwh + margin,
            price.values,
            predicted_start_soc,
            "pwl",
            pwl_curve=(curve["grid"], curve["values"]),
        )
    return DayPlan(
        day=day,
        decision_time=issue,
        predicted_start_soc=float(predicted_start_soc),
        forecast=forecast,
        margin=margin,
        price_forecast=price,
        q=np.asarray(solved["q"], dtype=float),
        allow_storage=True,
        max_lp_residual=float(solved["max_residual"]),
    )


def make_cold_plan(dataset: core.Dataset, day: int, soc: float) -> DayPlan:
    q = np.maximum(dataset.cold_load_kwh - dataset.cold_pv_kwh, 0.0)
    forecast = core.Forecast(
        load_kwh=dataset.cold_load_kwh.copy(),
        pv_kwh=dataset.cold_pv_kwh.copy(),
        source_max_timestamp=None,
        source_rule="declared_attachment1_cold_start",
    )
    dummy_price = PriceForecast(
        target_day=day,
        issue_time=dataset.dates[day],
        values=np.full(core.N_STEPS, np.nan),
        source_times=pd.DatetimeIndex([dataset.dates[day]] * core.N_STEPS),
        current_actual_step=None,
    )
    return DayPlan(
        day=day,
        decision_time=dataset.dates[day],
        predicted_start_soc=float(soc),
        forecast=forecast,
        margin=np.zeros(core.N_STEPS),
        price_forecast=dummy_price,
        q=q,
        allow_storage=False,
        max_lp_residual=0.0,
    )


def execute_step(
    dataset: core.Dataset,
    actual_price: np.ndarray,
    plan: DayPlan,
    step: int,
    soc: float,
) -> Dict[str, object]:
    load = float(dataset.load_kwh[plan.day, step])
    pv = float(dataset.pv_kwh[plan.day, step])
    q = float(plan.q[step])
    if plan.allow_storage:
        action = core.feedback_step(soc, q, load, pv)
    else:
        balance = q + pv - load
        action = {
            "charge_kwh": 0.0,
            "discharge_kwh": 0.0,
            "emergency_kwh": max(-balance, 0.0),
            "unused_supply_kwh": max(balance, 0.0),
            "soc_after_kwh": float(soc),
        }
    start = dataset.interval_starts(plan.day)[step]
    price_f = None if not plan.allow_storage else float(plan.price_forecast.values[step])
    price_a = float(actual_price[plan.day, step])
    return {
        "interval_start": start,
        "interval_end": start + pd.Timedelta(minutes=10),
        "plan_day": dataset.dates[plan.day],
        "step": int(step),
        "phase": "dynamic" if plan.allow_storage else "cold_start",
        "decision_time": plan.decision_time,
        "price_forecast_yuan_per_kwh": price_f,
        "price_actual_yuan_per_kwh": price_a,
        "price_max_source_time": None if not plan.allow_storage else plan.price_forecast.max_source_time,
        "load_actual_kwh": load,
        "pv_actual_kwh": pv,
        "load_forecast_kwh": float(plan.forecast.load_kwh[step]),
        "pv_forecast_kwh": float(plan.forecast.pv_kwh[step]),
        "plan_grid_kwh": q,
        "charge_kwh": float(action["charge_kwh"]),
        "discharge_kwh": float(action["discharge_kwh"]),
        "emergency_kwh": float(action["emergency_kwh"]),
        "unused_supply_kwh": float(action["unused_supply_kwh"]),
        "soc_before_kwh": float(soc),
        "soc_after_kwh": float(action["soc_after_kwh"]),
        "plan_cost_actual_yuan": price_a * q,
        "emergency_cost_actual_yuan": 5.0 * price_a * float(action["emergency_kwh"]),
    }


def build_warm_context(last_day: int = 30) -> WarmContext:
    dataset = core.load_dataset()
    actual_price = load_actual_prices(dataset)
    combo = ("same_weekday_2w", "recent_5d")
    library = q2full.build_forecast_library(dataset, [combo])
    records = []
    decisions = []
    soc_midnight = core.INITIAL_SOC_KWH
    previous: Optional[DayPlan] = None
    for day in range(last_day + 1):
        predicted_start = (
            core.INITIAL_SOC_KWH if previous is None
            else predict_plan_start(soc_midnight, previous)
        )
        plan = (
            make_cold_plan(dataset, day, predicted_start)
            if day < COLD_START_DAYS
            else make_dynamic_plan(dataset, actual_price, library, combo, day, predicted_start)
        )
        if previous is None:
            actual_start = core.INITIAL_SOC_KWH
        else:
            bridge = execute_step(dataset, actual_price, previous, core.N_STEPS - 1, soc_midnight)
            records.append(bridge)
            actual_start = float(bridge["soc_after_kwh"])
        soc = actual_start
        for step in range(core.N_STEPS - 1):
            row = execute_step(dataset, actual_price, plan, step, soc)
            records.append(row)
            soc = float(row["soc_after_kwh"])
        decisions.append({
            "day": day,
            "date": dataset.dates[day],
            "phase": "dynamic" if plan.allow_storage else "cold_start",
            "soc_midnight_kwh": soc_midnight,
            "predicted_start_soc_kwh": predicted_start,
            "actual_start_soc_kwh": actual_start,
            "price_max_source_time": None if not plan.allow_storage else plan.price_forecast.max_source_time,
            "max_lp_residual_kwh": plan.max_lp_residual,
        })
        soc_midnight = soc
        previous = plan
    if previous is None:
        raise AssertionError("暖启动未生成任何计划")
    log = pd.DataFrame(records).sort_values("interval_start", kind="stable").reset_index(drop=True)
    return WarmContext(
        soc_midnight=float(soc_midnight),
        previous=previous,
        log=log,
        decisions=pd.DataFrame(decisions),
    )


def clone_dataset_with_price(dataset: core.Dataset, price: np.ndarray) -> core.Dataset:
    return copy.deepcopy(dataset).__class__(
        dates=dataset.dates,
        input_time_labels=dataset.input_time_labels,
        template_labels=dataset.template_labels,
        price=np.asarray(price, dtype=float),
        load_kw=dataset.load_kw,
        pv_kw=dataset.pv_kw,
        load_kwh=dataset.load_kwh,
        pv_kwh=dataset.pv_kwh,
        cold_load_kwh=dataset.cold_load_kwh,
        cold_pv_kwh=dataset.cold_pv_kwh,
    )


def solve_adjustment_strict(
    q0: np.ndarray,
    forecast,
    margin: np.ndarray,
    start_soc: float,
    block: Tuple[int, int],
    price_forecast: np.ndarray,
    terminal_curve: Tuple[np.ndarray, np.ndarray],
) -> Dict[str, object]:
    """Q3 settlement-B adjustment LP; every solver failure is fatal."""
    steps = np.asarray(forecast.steps, dtype=int)
    n = len(steps)
    ou, or_, oc, od, oh, ow = 0, n, 2 * n, 3 * n, 4 * n, 5 * n
    oe, oz = 6 * n, 7 * n + 1
    nvar = oz + 1
    obj = np.zeros(nvar)
    p = np.asarray(price_forecast, dtype=float)[steps]
    obj[ou:ou + n] = 1.5 * p
    obj[or_:or_ + n] = -0.5 * p
    obj[oc:oc + n] = core.EPS_THROUGHPUT
    obj[od:od + n] = core.EPS_THROUGHPUT
    obj[oh:oh + n] = 5.0 * p
    obj[oz] = 1.0

    aeq = sparse.lil_matrix((2 * n, nvar))
    beq = np.zeros(2 * n)
    risk_net = forecast.net_kwh + margin
    for k, step in enumerate(steps):
        aeq[k, ou + k] = 1.0
        aeq[k, or_ + k] = -1.0
        aeq[k, oc + k] = -1.0
        aeq[k, od + k] = 1.0
        aeq[k, oh + k] = 1.0
        aeq[k, ow + k] = -1.0
        beq[k] = float(risk_net[k] - q0[step])
        row = n + k
        aeq[row, oe + k] = -1.0
        aeq[row, oe + k + 1] = 1.0
        aeq[row, oc + k] = -core.ETA_CHARGE
        aeq[row, od + k] = 1.0 / core.ETA_DISCHARGE

    grid, values = terminal_curve
    slopes = np.diff(values) / np.diff(grid)
    intercepts = values[:-1] - slopes * grid[:-1]
    aub = sparse.lil_matrix((len(slopes), nvar))
    bub = np.zeros(len(slopes))
    for k, (slope, intercept) in enumerate(zip(slopes, intercepts)):
        aub[k, oe + n] = float(slope)
        aub[k, oz] = -1.0
        bub[k] = -float(intercept)

    bounds = []
    bounds.extend([
        (0.0, None) if block[0] <= step < block[1] else (0.0, 0.0)
        for step in steps
    ])
    bounds.extend([
        (0.0, float(q0[step])) if block[0] <= step < block[1] else (0.0, 0.0)
        for step in steps
    ])
    bounds.extend([(0.0, core.STEP_LIMIT_KWH)] * n)
    bounds.extend([(0.0, core.STEP_LIMIT_KWH)] * n)
    bounds.extend([(0.0, None)] * n)
    bounds.extend([(0.0, None)] * n)
    bounds.extend([(core.SOC_MIN_KWH, core.SOC_MAX_KWH)] * (n + 1))
    bounds.append((0.0, None))
    bounds[oe] = (float(start_soc), float(start_soc))

    result = linprog(
        obj,
        A_ub=aub.tocsr(),
        b_ub=bub,
        A_eq=aeq.tocsr(),
        b_eq=beq,
        bounds=bounds,
        method="highs",
    )
    if not result.success:
        raise RuntimeError(
            f"Q4调整LP失败 day={forecast.day_index} release={forecast.release_hour}: {result.message}"
        )
    x = np.asarray(result.x)
    u, r = x[ou:ou + n], x[or_:or_ + n]
    candidate = np.asarray(q0, dtype=float).copy()
    candidate[steps] = q0[steps] + u - r
    eq_res = np.asarray(aeq.tocsr() @ x - beq)
    ub_res = np.maximum(np.asarray(aub.tocsr() @ x - bub), 0.0)
    return {
        "candidate": candidate,
        "charge": x[oc:oc + n],
        "discharge": x[od:od + n],
        "planned_emergency": x[oh:oh + n],
        "max_residual": float(max(np.abs(eq_res).max(), ub_res.max())),
    }


def block_score_b(
    q: np.ndarray,
    q0: np.ndarray,
    block: Tuple[int, int],
    start_soc: float,
    forecast_net: np.ndarray,
    scenarios: np.ndarray,
    price_forecast: np.ndarray,
) -> float:
    start, end = block
    u = np.maximum(q[start:end] - q0[start:end], 0.0)
    r = np.maximum(q0[start:end] - q[start:end], 0.0)
    ordinary = float(np.sum(
        price_forecast[start:end] * q0[start:end]
        + 1.5 * price_forecast[start:end] * u
        - 0.5 * price_forecast[start:end] * r
    ))
    if len(scenarios) == 0:
        raise AssertionError("经济门历史场景不足，禁止静默接受调整")
    lam = core.ETA_DISCHARGE * float(np.median(price_forecast))
    scores = []
    for residual in scenarios:
        soc = float(start_soc)
        emergency_cost = 0.0
        for local, step in enumerate(range(start, end)):
            net = float(forecast_net[local] + residual[local])
            action = core.feedback_step(
                soc, float(q[step]), max(net, 0.0), max(-net, 0.0)
            )
            soc = float(action["soc_after_kwh"])
            emergency_cost += 5.0 * price_forecast[step] * action["emergency_kwh"]
        scores.append(ordinary + emergency_cost - lam * soc)
    return float(np.mean(scores))


def ledger_b(
    q0: np.ndarray,
    qfinal: np.ndarray,
    price_actual: np.ndarray,
    emergency: np.ndarray,
) -> Dict[str, float]:
    u = np.maximum(qfinal - q0, 0.0)
    r = np.maximum(q0 - qfinal, 0.0)
    base = float(np.dot(price_actual, q0))
    up = float(np.dot(1.5 * price_actual, u))
    refund = float(np.dot(-0.5 * price_actual, r))
    emergency_cost = float(np.dot(5.0 * price_actual, emergency))
    return {
        "base_plan_cost_yuan": base,
        "up_adjustment_cost_yuan": up,
        "down_refund_B_yuan": refund,
        "ordinary_cost_B_yuan": base + up + refund,
        "emergency_cost_yuan": emergency_cost,
        "total_cash_B_yuan": base + up + refund + emergency_cost,
    }
