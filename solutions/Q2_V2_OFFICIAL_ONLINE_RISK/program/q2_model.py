from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.sparse import csr_matrix, lil_matrix, vstack


MATERIAL_ROOT = Path(__file__).resolve().parent / "data" / "附件"
ATTACHMENT1 = MATERIAL_ROOT / "附件1.xlsx"
ATTACHMENT2 = MATERIAL_ROOT / "附件2.xlsx"
RESULT2_TEMPLATE = MATERIAL_ROOT / "附件5" / "result2.xlsx"

T = 144
DT = 1.0 / 6.0
ETA_C = ETA_D = 0.9
E_MIN, E_MAX, E_INIT = 1200.0, 10800.0, 6000.0
Q_MAX = 5000.0 * DT
K_EMERGENCY = 5.0
TEST_DAYS = np.arange(31, 365)


@dataclass
class Q2Data:
    dates: pd.DatetimeIndex
    price: np.ndarray
    load: np.ndarray
    pv: np.ndarray
    source_labels: list[str]


def load_data() -> Q2Data:
    a1 = pd.read_excel(ATTACHMENT1)
    if a1.shape[0] != T or a1.shape[1] < 2:
        raise ValueError(f"附件1形状异常：{a1.shape}")
    price = a1.iloc[:, 1].to_numpy(float)
    source_labels = [str(v) for v in a1.iloc[:, 0].tolist()]

    load_df = pd.read_excel(ATTACHMENT2, sheet_name=0, index_col=0)
    pv_df = pd.read_excel(ATTACHMENT2, sheet_name=1, index_col=0)
    load = load_df.to_numpy(float)
    pv = pv_df.to_numpy(float)
    dates = pd.DatetimeIndex(pd.to_datetime(load_df.index))
    if load.shape != (365, T) or pv.shape != (365, T):
        raise ValueError(f"附件2形状异常：load={load.shape}, pv={pv.shape}")
    if not load_df.index.equals(pv_df.index):
        raise ValueError("附件2负荷与光伏日期不一致")
    if np.isnan(load).any() or np.isnan(pv).any() or np.isnan(price).any():
        raise ValueError("输入数据存在缺失值")
    return Q2Data(dates=dates, price=price, load=load, pv=pv, source_labels=source_labels)


def build_forecasts(data: Q2Data) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    load, pv = data.load, data.pv
    load_fc: dict[str, np.ndarray] = {}
    pv_fc: dict[str, np.ndarray] = {}

    for weeks in (1, 2, 3, 4):
        pred = np.full_like(load, np.nan)
        for day in range(7 * weeks, len(load)):
            pred[day] = load[[day - 7 * j for j in range(1, weeks + 1)]].mean(axis=0)
        load_fc[f"same_weekday_{weeks}w"] = pred

    for days in (1, 2, 3, 5):
        pred = np.full_like(pv, np.nan)
        for day in range(days, len(pv)):
            pred[day] = pv[day - days:day].mean(axis=0)
        pv_fc[f"recent_{days}d"] = pred
    pred = np.full_like(pv, np.nan)
    pred[7:] = pv[:-7]
    pv_fc["same_weekday_1w"] = pred
    return load_fc, pv_fc


def forecast_benchmark(data: Q2Data, load_fc: dict[str, np.ndarray], pv_fc: dict[str, np.ndarray]) -> pd.DataFrame:
    rows: list[dict] = []
    actual_l, actual_pv = data.load[TEST_DAYS], data.pv[TEST_DAYS]
    for name, pred in load_fc.items():
        f = pred[TEST_DAYS]
        err = f - actual_l
        rows.append({
            "target": "load", "method": name,
            "WAPE_pct": 100.0 * np.abs(err).sum() / actual_l.sum(),
            "RMSE_kW": float(np.sqrt(np.mean(err**2))),
            "MAE_kW": float(np.mean(np.abs(err))),
        })
    for name, pred in pv_fc.items():
        f = pred[TEST_DAYS]
        err = f - actual_pv
        daylight = actual_pv > 1e-9
        rows.append({
            "target": "pv", "method": name,
            "WAPE_pct": 100.0 * np.abs(err[daylight]).sum() / actual_pv[daylight].sum(),
            "RMSE_kW": float(np.sqrt(np.mean(err[daylight]**2))),
            "MAE_kW": float(np.mean(np.abs(err[daylight]))),
        })
    return pd.DataFrame(rows)


def deterministic_plan(price: np.ndarray, load_fc: np.ndarray, pv_fc: np.ndarray, e0: float,
                       cyclic: bool = True, lex: bool = True,
                       terminal_target: float | None = None,
                       terminal_penalty: float | None = None,
                       terminal_band: tuple[float, float] | None = None) -> np.ndarray:
    # x=[g,c,d,w,E]；显式w保证能量平衡可审计。
    ig, ic, id_, iw, iE = 0, T, 2 * T, 3 * T, 4 * T
    use_soft = terminal_penalty is not None
    n = 5 * T + 1 + (2 if use_soft else 0)
    obj = np.zeros(n)
    obj[ig:ig + T] = price
    if use_soft:
        obj[5*T+1:5*T+3] = float(terminal_penalty)

    has_terminal = cyclic or (terminal_target is not None and not use_soft)
    aeq = lil_matrix((2 * T + (1 if has_terminal else 0) + (1 if use_soft else 0), n), dtype=float)
    beq = np.zeros(aeq.shape[0])
    for k in range(T):
        # g + pv*dt + d = load*dt + c + w
        aeq[k, ig + k] = 1.0
        aeq[k, ic + k] = -1.0
        aeq[k, id_ + k] = 1.0
        aeq[k, iw + k] = -1.0
        beq[k] = (load_fc[k] - pv_fc[k]) * DT
        aeq[T + k, iE + k + 1] = 1.0
        aeq[T + k, iE + k] = -1.0
        aeq[T + k, ic + k] = -ETA_C
        aeq[T + k, id_ + k] = 1.0 / ETA_D
    if has_terminal:
        aeq[2 * T, iE + T] = 1.0
        beq[2 * T] = e0 if terminal_target is None else terminal_target
    if use_soft:
        rr = 2*T + (1 if has_terminal else 0)
        aeq[rr, iE+T] = 1.0; aeq[rr, 5*T+1] = -1.0; aeq[rr, 5*T+2] = 1.0
        beq[rr] = E_INIT if terminal_target is None else terminal_target

    lb = np.zeros(n)
    ub = np.full(n, np.inf)
    ub[ic:ic + T] = Q_MAX
    ub[id_:id_ + T] = Q_MAX
    lb[iE:iE + T + 1] = E_MIN
    ub[iE:iE + T + 1] = E_MAX
    lb[iE] = ub[iE] = e0
    bounds = list(zip(lb, ub))
    aub = None; bub = None
    if terminal_band is not None:
        lo, hi = terminal_band
        aub_lil = lil_matrix((2,n)); aub_lil[0,iE+T]=1; aub_lil[1,iE+T]=-1
        aub=csr_matrix(aub_lil); bub=np.array([hi,-lo])
    r1 = linprog(obj, A_ub=aub, b_ub=bub, A_eq=csr_matrix(aeq), b_eq=beq, bounds=bounds, method="highs")
    if not r1.success:
        raise RuntimeError(f"确定性计划第一层失败：{r1.message}")
    if not lex:
        return r1.x[ig:ig + T]

    obj2 = np.zeros(n)
    obj2[ic:ic + T] = 1.0
    obj2[id_:id_ + T] = 1.0
    cost_row = csr_matrix(obj.reshape(1, -1))
    r2 = linprog(
        obj2, A_ub=(cost_row if aub is None else vstack([aub,cost_row])),
        b_ub=([r1.fun + 1e-7] if bub is None else np.concatenate([bub,[r1.fun + 1e-7]])),
        A_eq=csr_matrix(aeq), b_eq=beq, bounds=bounds, method="highs",
    )
    if not r2.success:
        raise RuntimeError(f"确定性计划第二层失败：{r2.message}")
    return r2.x[ig:ig + T]


def settle_causally(g: np.ndarray, load: np.ndarray, pv: np.ndarray, e0: float) -> dict[str, np.ndarray]:
    c = np.zeros(T)
    d = np.zeros(T)
    emergency = np.zeros(T)
    spill = np.zeros(T)
    soc = np.zeros(T + 1)
    soc[0] = e0
    for k in range(T):
        balance = g[k] + pv[k] * DT - load[k] * DT
        if balance >= 0.0:
            c[k] = min(balance, Q_MAX, max(0.0, (E_MAX - soc[k]) / ETA_C))
            spill[k] = balance - c[k]
        else:
            d[k] = min(-balance, Q_MAX, max(0.0, ETA_D * (soc[k] - E_MIN)))
            emergency[k] = -balance - d[k]
        soc[k + 1] = soc[k] + ETA_C * c[k] - d[k] / ETA_D
    residual = g + pv * DT + d + emergency - load * DT - c - spill
    return {"g": g, "c": c, "d": d, "emergency": emergency, "spill": spill,
            "soc": soc, "balance_residual": residual}


def settle_planned_battery(g: np.ndarray, c_plan: np.ndarray, d_plan: np.ndarray,
                           load: np.ndarray, pv: np.ndarray,
                           e0: float) -> dict[str, np.ndarray]:
    """Execute a fully pre-planned battery schedule with physical projection.

    The day-ahead charge/discharge plan cannot use realized same-day data.  During
    execution, planned actions are clipped by physical feasibility; shortages are
    covered by emergency purchase and surplus is unutilized.  Emergency energy is
    never used to satisfy a planned charge.
    """
    c_plan = np.asarray(c_plan, dtype=float)
    d_plan = np.asarray(d_plan, dtype=float)
    steps = np.asarray(g).shape[0]
    if c_plan.shape != (steps,) or d_plan.shape != (steps,):
        raise ValueError("battery plans must match the grid-plan horizon")
    c = np.zeros(steps)
    d = np.zeros(steps)
    emergency = np.zeros(steps)
    spill = np.zeros(steps)
    soc = np.zeros(steps + 1)
    soc[0] = e0
    for k in range(steps):
        normal_supply = g[k] + pv[k] * DT
        demand = load[k] * DT
        if normal_supply >= demand:
            surplus = normal_supply - demand
            c[k] = min(
                max(c_plan[k], 0.0), surplus, Q_MAX,
                max(0.0, (E_MAX - soc[k]) / ETA_C),
            )
            spill[k] = surplus - c[k]
        else:
            deficit = demand - normal_supply
            d[k] = min(
                max(d_plan[k], 0.0), deficit, Q_MAX,
                max(0.0, ETA_D * (soc[k] - E_MIN)),
            )
            emergency[k] = deficit - d[k]
        soc[k + 1] = soc[k] + ETA_C * c[k] - d[k] / ETA_D
    residual = g + pv * DT + d + emergency - load * DT - c - spill
    return {"g": g, "c": c, "d": d, "emergency": emergency, "spill": spill,
            "soc": soc, "balance_residual": residual}


def net_residuals(data: Q2Data, load_pred: np.ndarray, pv_pred: np.ndarray) -> np.ndarray:
    actual_net = data.load - data.pv
    forecast_net = load_pred - pv_pred
    return actual_net - forecast_net


def rolling_margin(residuals: np.ndarray, day: int, alpha: float, window: int = 60,
                   structure: str = "time", block_hours: int = 2) -> np.ndarray:
    start = max(0, day - window)
    hist = residuals[start:day]
    valid = ~np.isnan(hist).any(axis=1)
    hist = hist[valid]
    if len(hist) == 0:
        return np.zeros(T)
    if structure == "global":
        margin = np.full(T, np.quantile(hist, alpha))
    elif structure == "time":
        margin = np.quantile(hist, alpha, axis=0)
    elif structure == "block":
        block = block_hours * 6
        margin = np.zeros(T)
        for start_slot in range(0, T, block):
            stop_slot = min(start_slot + block, T)
            margin[start_slot:stop_slot] = np.quantile(hist[:, start_slot:stop_slot], alpha)
    else:
        raise ValueError(f"未知分位结构：{structure}")
    return np.maximum(margin, 0.0)


def run_quantile_policy(data: Q2Data, load_pred: np.ndarray, pv_pred: np.ndarray, alpha: float,
                        days: np.ndarray = TEST_DAYS, window: int = 60,
                        structure: str = "time", block_hours: int = 2,
                        final_day_terminal_target: float | None = None,
                        initial_soc: float = E_INIT,
                        battery_interpretation: str = "A") -> dict:
    residuals = net_residuals(data, load_pred, pv_pred)
    arrays = {k: np.zeros((365, T)) for k in ("G", "C", "D", "Emergency", "Spill")}
    arrays["SOC"] = np.full((365, T + 1), np.nan)
    e0 = float(initial_soc)
    started = perf_counter()
    for position, day in enumerate(days):
        margin = rolling_margin(residuals, int(day), alpha, window, structure=structure,
                                block_hours=block_hours)
        risk_load = np.maximum(load_pred[day] + margin, 0.0)
        is_final_day = position == len(days) - 1 and final_day_terminal_target is not None
        g = deterministic_plan(
            data.price, risk_load, np.maximum(pv_pred[day], 0.0), e0,
            cyclic=not is_final_day,
            terminal_target=final_day_terminal_target if is_final_day else None,
        )
        if battery_interpretation == "A":
            actual = settle_causally(g, data.load[day], data.pv[day], e0)
        elif battery_interpretation == "B":
            if is_final_day:
                terminal, terminal_target = "hard", final_day_terminal_target
            else:
                terminal, terminal_target = "hard", e0
            battery_plan = plan_battery_for_fixed_grid(
                data.price, risk_load, np.maximum(pv_pred[day], 0.0), e0,
                g, terminal=terminal, terminal_target=terminal_target,
            )
            actual = settle_planned_battery(
                g, battery_plan["c"], battery_plan["d"],
                data.load[day], data.pv[day], e0,
            )
        else:
            raise ValueError(f"unknown battery interpretation: {battery_interpretation}")
        arrays["G"][day] = g
        arrays["C"][day] = actual["c"]
        arrays["D"][day] = actual["d"]
        arrays["Emergency"][day] = actual["emergency"]
        arrays["Spill"][day] = actual["spill"]
        arrays["SOC"][day] = actual["soc"]
        e0 = actual["soc"][-1]
    summary = summarize_policy(
        data, arrays, days, perf_counter() - started,
        model=f"quantile_{structure}_w{window}_a{alpha:.2f}",
    )
    summary["battery_interpretation"] = battery_interpretation
    return summary | {"arrays": arrays}


def make_scenarios(data: Q2Data, load_pred: np.ndarray, pv_pred: np.ndarray, day: int,
                   count: int = 12, window: int = 60) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    start = max(0, day - window)
    candidates = [j for j in range(start, day)
                  if not np.isnan(load_pred[j]).any() and not np.isnan(pv_pred[j]).any()]
    if not candidates:
        return load_pred[day][None, :], pv_pred[day][None, :], np.array([1.0])
    rng = np.random.default_rng(20260911 + day * 1000 + count)
    chosen = rng.choice(np.asarray(candidates, dtype=int), size=count,
                        replace=count > len(candidates))
    load_sc = np.maximum(load_pred[day] + (data.load[chosen] - load_pred[chosen]), 0.0)
    pv_sc = np.maximum(pv_pred[day] + (data.pv[chosen] - pv_pred[chosen]), 0.0)
    pv_sc[:, pv_pred[day] <= 1e-9] = 0.0
    weights = np.full(count, 1.0 / count)
    return load_sc, pv_sc, weights


def two_stage_plan(price: np.ndarray, load_sc: np.ndarray, pv_sc: np.ndarray, weights: np.ndarray,
                   e0: float, terminal: str = "hard", terminal_lambda: float = 0.0,
                   terminal_target: float | None = None,
                   fixed_g: np.ndarray | None = None,
                   cvar_beta: float = 0.0, cvar_weight: float = 0.0,
                   return_full_plan: bool = False):
    """分流两阶段LP。terminal可取hard、continuous或value。"""
    scenarios = load_sc.shape[0]
    ng = T
    # 每场景变量：[x,c,d,h,w,E]，x为普通能源实际服务负荷的电量。
    block = 5 * T + (T + 1)
    n_base = ng + scenarios * block
    use_cvar = cvar_weight > 0.0
    iz = n_base
    iu = n_base + 1
    n = n_base + (1 + scenarios if use_cvar else 0)

    def offsets(s: int) -> tuple[int, int, int, int, int, int]:
        o = ng + s * block
        return o, o + T, o + 2 * T, o + 3 * T, o + 4 * T, o + 5 * T

    obj = np.zeros(n)
    obj[:T] = price
    if use_cvar:
        if not 0.0 < cvar_beta < 1.0:
            raise ValueError("cvar_beta must be in (0,1)")
        obj[iz] = cvar_weight
        obj[iu:iu + scenarios] = cvar_weight * weights / (1.0 - cvar_beta)
    eq_per_scenario = 3 * T + (2 if terminal == "hard" else 1)
    aeq = lil_matrix((scenarios * eq_per_scenario, n), dtype=float)
    beq = np.zeros(scenarios * eq_per_scenario)
    row = 0
    for s in range(scenarios):
        iy, ic, id_, ie, iw, iE = offsets(s)
        obj[ie:ie + T] = weights[s] * K_EMERGENCY * price
        if terminal == "value":
            obj[iE + T] = -weights[s] * terminal_lambda
        for k in range(T):
            # 普通能源平衡：g+PV+d = x+c+w。
            aeq[row, iy + k] = 1.0
            aeq[row, ic + k] = 1.0
            aeq[row, iw + k] = 1.0
            aeq[row, id_ + k] = -1.0
            aeq[row, k] = -1.0
            beq[row] = pv_sc[s, k] * DT
            row += 1
            # 负荷满足：x+h=Load。h只进入负荷方程。
            aeq[row, iy + k] = 1.0
            aeq[row, ie + k] = 1.0
            beq[row] = load_sc[s, k] * DT
            row += 1
            aeq[row, iE + k + 1] = 1.0
            aeq[row, iE + k] = -1.0
            aeq[row, ic + k] = -ETA_C
            aeq[row, id_ + k] = 1.0 / ETA_D
            row += 1
        aeq[row, iE] = 1.0
        beq[row] = e0
        row += 1
        if terminal == "hard":
            aeq[row, iE + T] = 1.0
            beq[row] = e0 if terminal_target is None else terminal_target
            row += 1

    # CVaR约束：scenario emergency cost - z - u_s <= 0。
    aub = None; bub = None
    if use_cvar:
        aub_lil = lil_matrix((scenarios, n), dtype=float)
        for s in range(scenarios):
            _, _, _, ie, _, _ = offsets(s)
            aub_lil[s, ie:ie + T] = K_EMERGENCY * price
            aub_lil[s, iz] = -1.0
            aub_lil[s, iu + s] = -1.0
        aub = csr_matrix(aub_lil); bub = np.zeros(scenarios)

    lb = np.zeros(n)
    ub = np.full(n, np.inf)
    if fixed_g is not None:
        fixed_g = np.asarray(fixed_g, dtype=float)
        if fixed_g.shape != (T,):
            raise ValueError("fixed_g must have shape (144,)")
        lb[:T] = fixed_g
        ub[:T] = fixed_g
    for s in range(scenarios):
        iy, ic, id_, _, _, iE = offsets(s)
        ub[iy:iy + T] = load_sc[s] * DT
        ub[ic:ic + T] = Q_MAX
        ub[id_:id_ + T] = Q_MAX
        lb[iE:iE + T + 1] = E_MIN
        ub[iE:iE + T + 1] = E_MAX

    started = perf_counter()
    aeq_csr = csr_matrix(aeq)
    result = linprog(obj, A_ub=aub, b_ub=bub, A_eq=aeq_csr, b_eq=beq,
                     bounds=list(zip(lb, ub)), method="highs")
    if not result.success:
        raise RuntimeError(f"两阶段LP失败：{result.message}")

    # 物理修正：依据第一遍共同计划判断每个场景每时段是正常电源富余还是缺口。
    # 富余时段仅允许充电或形成未利用剩余供给；缺口时段仅允许放电/紧急购电。
    # 迭代更新分类，避免“计划电去充电、同时由紧急电供负荷”的间接套利。
    physical_iterations = 0
    previous_classification = None
    for physical_iterations in range(1, 7):
        g_now = result.x[:T]
        classification = np.vstack([
            g_now + pv_sc[s] * DT - load_sc[s] * DT >= -1e-9
            for s in range(scenarios)
        ])
        if previous_classification is not None and np.array_equal(classification, previous_classification):
            break
        previous_classification = classification.copy()
        ub_phys = ub.copy()
        for s in range(scenarios):
            _, ic, id_, ie, _, _ = offsets(s)
            surplus = classification[s]
            ub_phys[ic:ic + T][~surplus] = 0.0
            ub_phys[id_:id_ + T][surplus] = 0.0
            ub_phys[ie:ie + T][surplus] = 0.0
        corrected = linprog(obj, A_ub=aub, b_ub=bub, A_eq=aeq_csr, b_eq=beq,
                            bounds=list(zip(lb, ub_phys)), method="highs")
        if not corrected.success:
            raise RuntimeError(f"两阶段LP物理修正失败：{corrected.message}")
        result = corrected
    simultaneous = 0
    max_residual = 0.0
    emergency_charge_violation = 0.0
    for s in range(scenarios):
        iy, ic, id_, ie, iw, _ = offsets(s)
        c = result.x[ic:ic + T]
        d = result.x[id_:id_ + T]
        emergency = result.x[ie:ie + T]
        simultaneous += int(np.sum((c > 1e-7) & (d > 1e-7)))
        emergency_charge_violation = max(
            emergency_charge_violation,
            float(np.max(np.minimum(c, emergency))),
        )
        pool = (result.x[iy:iy + T] + c + result.x[iw:iw + T]
                - result.x[id_:id_ + T] - result.x[:T] - pv_sc[s] * DT)
        max_residual = max(max_residual, float(np.max(np.abs(pool))))
    diagnostics = {
        "solver_objective": float(result.fun),
        "solve_seconds": perf_counter() - started,
        "scenario_count": scenarios,
        "terminal": terminal,
        "terminal_lambda": terminal_lambda,
        "terminal_target": terminal_target,
        "fixed_first_stage": fixed_g is not None,
        "cvar_beta": cvar_beta,
        "cvar_weight": cvar_weight,
        "physical_iterations": physical_iterations,
        "recourse_simultaneous_charge_discharge_count": simultaneous,
        "emergency_charge_path_violation": emergency_charge_violation,
        "max_source_pool_residual": max_residual,
    }
    first_stage = result.x[:T]
    if return_full_plan:
        _, ic, id_, _, _, _ = offsets(0)
        return first_stage, diagnostics, {
            "c": result.x[ic:ic + T].copy(),
            "d": result.x[id_:id_ + T].copy(),
        }
    return first_stage, diagnostics


def plan_battery_for_fixed_grid(price: np.ndarray, load_pred: np.ndarray,
                                pv_pred: np.ndarray, e0: float, g: np.ndarray,
                                terminal: str = "value",
                                terminal_lambda: float = 0.0,
                                terminal_target: float | None = None) -> dict[str, np.ndarray]:
    """Create one causal battery plan after the grid plan has been frozen."""
    _, _, plan = two_stage_plan(
        price,
        np.asarray(load_pred, dtype=float)[None, :],
        np.maximum(np.asarray(pv_pred, dtype=float)[None, :], 0.0),
        np.array([1.0]),
        e0,
        terminal=terminal,
        terminal_lambda=terminal_lambda,
        terminal_target=terminal_target,
        fixed_g=np.asarray(g, dtype=float),
        return_full_plan=True,
    )
    return plan


def run_stochastic_policy(data: Q2Data, load_pred: np.ndarray, pv_pred: np.ndarray,
                          days: np.ndarray = TEST_DAYS, scenario_count: int = 12,
                          window: int = 60, terminal: str = "hard",
                          terminal_lambda: float = 0.0,
                          final_day_terminal_target: float | None = None,
                          scenario_factory=None, cvar_beta: float = 0.0,
                          cvar_weight: float = 0.0,
                          initial_soc: float = E_INIT,
                          battery_interpretation: str = "A") -> dict:
    arrays = {k: np.zeros((365, T)) for k in ("G", "C", "D", "Emergency", "Spill")}
    arrays["SOC"] = np.full((365, T + 1), np.nan)
    e0 = float(initial_soc)
    diagnostics: list[dict] = []
    started = perf_counter()
    for pos, day in enumerate(days):
        factory = make_scenarios if scenario_factory is None else scenario_factory
        load_sc, pv_sc, weights = factory(
            data, load_pred, pv_pred, int(day), count=scenario_count, window=window,
        )
        is_final_day = pos == len(days) - 1 and final_day_terminal_target is not None
        day_terminal = "hard" if is_final_day else terminal
        g, diag = two_stage_plan(
            data.price, load_sc, pv_sc, weights, e0,
            terminal=day_terminal,
            terminal_lambda=terminal_lambda if not is_final_day else 0.0,
            terminal_target=final_day_terminal_target if is_final_day else None,
            cvar_beta=cvar_beta, cvar_weight=cvar_weight,
        )
        diag["day_index"] = int(day)
        diagnostics.append(diag)
        if battery_interpretation == "A":
            actual = settle_causally(g, data.load[day], data.pv[day], e0)
        elif battery_interpretation == "B":
            expected_load = np.average(load_sc, axis=0, weights=weights)
            expected_pv = np.average(pv_sc, axis=0, weights=weights)
            battery_plan = plan_battery_for_fixed_grid(
                data.price, expected_load, expected_pv, e0, g,
                terminal=day_terminal,
                terminal_lambda=terminal_lambda if not is_final_day else 0.0,
                terminal_target=(
                    final_day_terminal_target if is_final_day else None
                ),
            )
            actual = settle_planned_battery(
                g, battery_plan["c"], battery_plan["d"],
                data.load[day], data.pv[day], e0,
            )
        else:
            raise ValueError(f"unknown battery interpretation: {battery_interpretation}")
        arrays["G"][day] = g
        arrays["C"][day] = actual["c"]
        arrays["D"][day] = actual["d"]
        arrays["Emergency"][day] = actual["emergency"]
        arrays["Spill"][day] = actual["spill"]
        arrays["SOC"][day] = actual["soc"]
        e0 = actual["soc"][-1]
        if (pos + 1) % 25 == 0 or pos + 1 == len(days):
            print(f"two-stage progress {pos + 1}/{len(days)}")
    summary = summarize_policy(data, arrays, days, perf_counter() - started,
                               model=f"two_stage_{scenario_count}_{terminal}")
    summary["battery_interpretation"] = battery_interpretation
    summary["mean_daily_lp_seconds"] = float(np.mean([d["solve_seconds"] for d in diagnostics]))
    summary["max_source_pool_residual"] = float(max(d["max_source_pool_residual"] for d in diagnostics))
    summary["recourse_simultaneous_charge_discharge_count"] = int(sum(
        d["recourse_simultaneous_charge_discharge_count"] for d in diagnostics
    ))
    summary["emergency_charge_path_violation"] = float(max(
        d["emergency_charge_path_violation"] for d in diagnostics
    ))
    return summary | {"arrays": arrays, "diagnostics": diagnostics}


def summarize_policy(data: Q2Data, arrays: dict[str, np.ndarray], days: np.ndarray,
                     runtime: float, model: str) -> dict:
    g = arrays["G"][days]
    emergency = arrays["Emergency"][days]
    spill = arrays["Spill"][days]
    c = arrays["C"][days]
    d = arrays["D"][days]
    soc = arrays["SOC"][days]
    plan_cost = float(np.sum(g * data.price))
    emergency_cost = float(np.sum(emergency * data.price * K_EMERGENCY))
    continuity = []
    for idx in range(1, len(days)):
        continuity.append(abs(soc[idx - 1, -1] - soc[idx, 0]))
    residual = g + data.pv[days] * DT + d + emergency - data.load[days] * DT - c - spill
    soc_residual = soc[:, 1:] - soc[:, :-1] - ETA_C * c + d / ETA_D
    return {
        "model": model,
        "days": int(len(days)),
        "plan_cost_yuan": plan_cost,
        "emergency_cost_yuan": emergency_cost,
        "total_cost_yuan": plan_cost + emergency_cost,
        "total_cost_10k_yuan": (plan_cost + emergency_cost) / 10000.0,
        "grid_purchase_kwh": float(g.sum()),
        "emergency_kwh": float(emergency.sum()),
        "emergency_intervals": int(np.sum(emergency > 1e-7)),
        "emergency_days": int(np.sum(emergency.sum(axis=1) > 1e-7)),
        "spill_kwh": float(spill.sum()),
        "charge_kwh": float(c.sum()),
        "discharge_kwh": float(d.sum()),
        "soc_min_kwh": float(np.nanmin(soc)),
        "soc_max_kwh": float(np.nanmax(soc)),
        "end_soc_kwh": float(soc[-1, -1]),
        "cross_day_soc_residual_kwh": float(max(continuity, default=0.0)),
        "balance_residual_kwh": float(np.max(np.abs(residual))),
        "soc_residual_kwh": float(np.nanmax(np.abs(soc_residual))),
        "simultaneous_actual_intervals": int(np.sum((c > 1e-7) & (d > 1e-7))),
        "solver_failures": 0,
        "runtime_seconds": float(runtime),
    }


def run_point_policy(data: Q2Data, load_pred: np.ndarray, pv_pred: np.ndarray,
                     days: np.ndarray = TEST_DAYS, model: str = "point_forecast",
                     final_day_terminal_target: float | None = None,
                     initial_soc: float = E_INIT) -> dict:
    arrays = {k: np.zeros((365, T)) for k in ("G", "C", "D", "Emergency", "Spill")}
    arrays["SOC"] = np.full((365, T + 1), np.nan)
    e0 = float(initial_soc)
    started = perf_counter()
    for position, day in enumerate(days):
        is_final_day = position == len(days) - 1 and final_day_terminal_target is not None
        g = deterministic_plan(
            data.price, load_pred[day], pv_pred[day], e0,
            cyclic=not is_final_day,
            terminal_target=final_day_terminal_target if is_final_day else None,
        )
        actual = settle_causally(g, data.load[day], data.pv[day], e0)
        for src, dst in [("g", "G"), ("c", "C"), ("d", "D"),
                         ("emergency", "Emergency"), ("spill", "Spill")]:
            arrays[dst][day] = actual[src]
        arrays["SOC"][day] = actual["soc"]
        e0 = actual["soc"][-1]
    return summarize_policy(data, arrays, days, perf_counter() - started, model) | {"arrays": arrays}


def run_oracle_policy(data: Q2Data, days: np.ndarray = TEST_DAYS,
                      final_day_terminal_target: float | None = None) -> dict:
    return run_point_policy(
        data, data.load, data.pv, days=days, model="oracle_perfect_information",
        final_day_terminal_target=final_day_terminal_target,
    )


def daily_frame(data: Q2Data, result: dict, days: np.ndarray = TEST_DAYS) -> pd.DataFrame:
    a = result["arrays"]
    rows = []
    for day in days:
        plan = float(a["G"][day] @ data.price)
        emergency = float(a["Emergency"][day] @ (K_EMERGENCY * data.price))
        rows.append({
            "date": data.dates[day], "plan_cost_yuan": plan,
            "emergency_cost_yuan": emergency, "total_cost_yuan": plan + emergency,
            "grid_kwh": float(a["G"][day].sum()),
            "emergency_kwh": float(a["Emergency"][day].sum()),
            "emergency_slots": int(np.sum(a["Emergency"][day] > 1e-7)),
            "spill_kwh": float(a["Spill"][day].sum()),
            "charge_kwh": float(a["C"][day].sum()),
            "discharge_kwh": float(a["D"][day].sum()),
            "soc_start_kwh": float(a["SOC"][day, 0]),
            "soc_end_kwh": float(a["SOC"][day, -1]),
        })
    return pd.DataFrame(rows)


def save_policy_npz(path: Path, result: dict) -> None:
    arrays = result["arrays"]
    np.savez_compressed(path, **arrays)
