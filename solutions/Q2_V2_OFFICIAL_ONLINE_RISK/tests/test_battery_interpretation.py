from __future__ import annotations

import numpy as np

from q2_model import (
    DT,
    ETA_C,
    ETA_D,
    settle_planned_battery,
)


def test_planned_battery_projection_balances_and_never_emergency_charges():
    g = np.array([100.0, 0.0, 100.0])
    c_plan = np.array([900.0, 900.0, 0.0])
    d_plan = np.array([0.0, 0.0, 900.0])
    load = np.array([600.0 * 6.0, 900.0 * 6.0, 300.0 * 6.0])
    pv = np.array([0.0, 600.0, 0.0])
    result = settle_planned_battery(g, c_plan, d_plan, load, pv, 6000.0)
    balance = (
        g + pv * DT + result["d"] + result["emergency"]
        - load * DT - result["c"] - result["spill"]
    )
    soc = result["soc"]
    soc_residual = soc[1:] - soc[:-1] - ETA_C * result["c"] + result["d"] / ETA_D
    assert np.max(np.abs(balance)) < 1e-9
    assert np.max(np.abs(soc_residual)) < 1e-9
    assert np.all((result["c"] <= 1e-9) | (result["emergency"] <= 1e-9))
