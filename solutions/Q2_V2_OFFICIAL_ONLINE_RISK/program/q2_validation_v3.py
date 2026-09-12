"""Independent primitives for the Q2 V3 validation package."""

from __future__ import annotations

import numpy as np
from scipy.optimize import linprog


def shift_right_endpoint_to_left_slots(values: np.ndarray) -> np.ndarray:
    """Rotate right-endpoint observations into the template's left-labeled slots."""
    return np.roll(np.asarray(values), -1, axis=-1)


def recompute_cost(grid: np.ndarray, emergency: np.ndarray, price: np.ndarray) -> dict[str, float]:
    """Recompute realized settlement cost from raw arrays only."""
    grid = np.asarray(grid, dtype=float)
    emergency = np.asarray(emergency, dtype=float)
    price = np.asarray(price, dtype=float)
    if grid.shape != emergency.shape or grid.shape[-1] != price.size:
        raise ValueError("grid, emergency and price shapes are inconsistent")
    plan = float(np.sum(grid * price))
    emergency_cost = float(np.sum(emergency * (5.0 * price)))
    return {
        "plan_cost_yuan": plan,
        "emergency_cost_yuan": emergency_cost,
        "total_cost_yuan": plan + emergency_cost,
    }


def solve_empirical_cvar(costs: np.ndarray, weights: np.ndarray, tau: float) -> dict:
    """Solve the standard weighted CVaR epigraph LP for fixed losses."""
    costs = np.asarray(costs, dtype=float).ravel()
    weights = np.asarray(weights, dtype=float).ravel()
    if costs.size == 0 or costs.shape != weights.shape:
        raise ValueError("costs and weights must be non-empty and equal length")
    if not np.isclose(weights.sum(), 1.0, atol=1e-12):
        raise ValueError("weights must sum to 1")
    if np.any(weights < 0) or not 0.0 < tau < 1.0:
        raise ValueError("weights must be nonnegative and tau must be in (0,1)")
    n = costs.size
    objective = np.r_[1.0, weights / (1.0 - tau)]
    a_ub = np.zeros((n, n + 1))
    a_ub[:, 0] = -1.0
    a_ub[:, 1:] = -np.eye(n)
    result = linprog(
        objective,
        A_ub=a_ub,
        b_ub=-costs,
        bounds=[(None, None)] + [(0.0, None)] * n,
        method="highs",
    )
    if not result.success:
        raise RuntimeError(result.message)
    return {
        "z": float(result.x[0]),
        "u": result.x[1:].copy(),
        "cvar": float(result.fun),
        "solver_status": result.message,
    }


def inventory_adjusted_cost(raw_cost_yuan: float, final_soc: float, *,
                            target_soc: float = 6000.0, value: float = 0.4684) -> float:
    """Value terminal inventory against one common shadow value (yuan/kWh)."""
    return float(raw_cost_yuan + value * (target_soc - final_soc))


def physical_audit(grid: np.ndarray, charge: np.ndarray, discharge: np.ndarray,
                   emergency: np.ndarray, spill: np.ndarray, soc: np.ndarray,
                   load: np.ndarray, pv: np.ndarray, *, dt: float = 1 / 6,
                   eta_c: float = 0.9, eta_d: float = 0.9) -> dict:
    """Return numerical physical evidence without consulting stored summaries."""
    arrays = [np.asarray(x, dtype=float) for x in
              (grid, charge, discharge, emergency, spill, soc, load, pv)]
    grid, charge, discharge, emergency, spill, soc, load, pv = arrays
    balance = grid + pv * dt + discharge + emergency - load * dt - charge - spill
    soc_residual = soc[:, 1:] - soc[:, :-1] - eta_c * charge + discharge / eta_d
    return {
        "max_balance_residual_kwh": float(np.nanmax(np.abs(balance))),
        "max_soc_recursion_residual_kwh": float(np.nanmax(np.abs(soc_residual))),
        "min_soc": float(np.nanmin(soc)),
        "max_soc": float(np.nanmax(soc)),
        "max_charge_interval_kwh": float(np.nanmax(charge)),
        "max_discharge_interval_kwh": float(np.nanmax(discharge)),
        "simultaneous_charge_discharge_count": int(np.sum((charge > 1e-7) & (discharge > 1e-7))),
        "emergency_to_battery_energy_kwh": float(np.sum(np.minimum(charge, emergency))),
        "emergency_to_battery_count": int(np.sum((charge > 1e-7) & (emergency > 1e-7))),
    }
