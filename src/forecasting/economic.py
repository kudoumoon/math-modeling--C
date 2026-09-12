"""Causal planning and cash-ledger simulation for economic forecast selection."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog


DT_HOURS = 1.0 / 6.0
N_INTERVALS = 144
E_MIN = 1200.0
E_MAX = 10800.0
P_MAX_ENERGY = 5000.0 * DT_HOURS
ETA_C = 0.90
ETA_D = 0.90


@dataclass(frozen=True)
class DayResult:
    planned_purchase: np.ndarray
    charge: np.ndarray
    discharge: np.ndarray
    emergency: np.ndarray
    surplus: np.ndarray
    end_energy: float
    normal_cost: float
    emergency_cost: float

    @property
    def cash_cost(self) -> float:
        return self.normal_cost + self.emergency_cost


def plan_day(
    risk_net_load_kw: np.ndarray,
    decision_price: np.ndarray,
    initial_energy: float,
    terminal_energy: float = 6000.0,
) -> np.ndarray:
    """Plan normal purchases with no access to future realizations."""
    net = np.asarray(risk_net_load_kw, dtype=float) * DT_HOURS
    price = np.asarray(decision_price, dtype=float)
    if net.shape != (N_INTERVALS,) or price.shape != (N_INTERVALS,):
        raise ValueError("daily inputs must contain exactly 144 intervals")
    n = N_INTERVALS
    q, c, d, w, e = (slice(i * n, (i + 1) * n) for i in range(5))
    objective = np.zeros(5 * n)
    objective[q] = price
    objective[c] = 1e-9
    objective[d] = 1e-9

    balance = np.zeros((n, 5 * n))
    rows = np.arange(n)
    balance[rows, q.start + rows] = 1.0
    balance[rows, d.start + rows] = 1.0
    balance[rows, c.start + rows] = -1.0
    balance[rows, w.start + rows] = -1.0

    state = np.zeros((n, 5 * n))
    state[rows, e.start + rows] = 1.0
    state[rows, c.start + rows] = -ETA_C
    state[rows, d.start + rows] = 1.0 / ETA_D
    state_rhs = np.zeros(n)
    state_rhs[0] = initial_energy
    if n > 1:
        state[np.arange(1, n), e.start + np.arange(n - 1)] = -1.0

    bounds = (
        [(0, None)] * n
        + [(0, P_MAX_ENERGY)] * n
        + [(0, P_MAX_ENERGY)] * n
        + [(0, None)] * n
        + [(E_MIN, E_MAX)] * (n - 1)
        + [(terminal_energy, terminal_energy)]
    )
    result = linprog(
        objective,
        A_eq=np.vstack([balance, state]),
        b_eq=np.concatenate([net, state_rhs]),
        bounds=bounds,
        method="highs",
    )
    if not result.success:
        raise RuntimeError(f"planning LP failed: {result.message}")
    return result.x[q]


def execute_day(
    planned_purchase: np.ndarray,
    actual_load_kw: np.ndarray,
    actual_pv_kw: np.ndarray,
    settlement_price: np.ndarray,
    initial_energy: float,
) -> DayResult:
    """Execute interval-by-interval using only current measurements and state."""
    q = np.asarray(planned_purchase, dtype=float)
    load = np.asarray(actual_load_kw, dtype=float) * DT_HOURS
    pv = np.asarray(actual_pv_kw, dtype=float) * DT_HOURS
    price = np.asarray(settlement_price, dtype=float)
    energy = float(initial_energy)
    charge = np.zeros(N_INTERVALS)
    discharge = np.zeros(N_INTERVALS)
    emergency = np.zeros(N_INTERVALS)
    surplus = np.zeros(N_INTERVALS)
    for t in range(N_INTERVALS):
        available = q[t] + pv[t] - load[t]
        if available >= 0:
            charge[t] = min(available, P_MAX_ENERGY, max(0.0, (E_MAX - energy) / ETA_C))
            energy += ETA_C * charge[t]
            surplus[t] = available - charge[t]
        else:
            deficit = -available
            discharge[t] = min(deficit, P_MAX_ENERGY, max(0.0, ETA_D * (energy - E_MIN)))
            energy -= discharge[t] / ETA_D
            emergency[t] = deficit - discharge[t]
    return DayResult(
        planned_purchase=q,
        charge=charge,
        discharge=discharge,
        emergency=emergency,
        surplus=surplus,
        end_energy=energy,
        normal_cost=float(np.dot(price, q)),
        emergency_cost=float(np.dot(5.0 * price, emergency)),
    )
