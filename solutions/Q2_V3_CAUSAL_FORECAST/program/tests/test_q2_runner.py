from __future__ import annotations

import numpy as np
import pandas as pd

from q2_model import Q2Data, settle_one_slot_delayed
from run_q2_v3 import (
    _recency_scenarios,
    candidate_grid,
    project_pending_energy,
    project_delayed_pending_energy,
    project_planned_pending_energy,
    release_mature_scores,
)


def synthetic_data() -> Q2Data:
    values = np.arange(8 * 144, dtype=float).reshape(8, 144)
    return Q2Data(
        dates=pd.date_range("2025-01-01", periods=8),
        price=np.ones(144),
        load=values + 1000.0,
        pv=values / 10.0,
        source_labels=[str(i) for i in range(144)],
    )


def test_scenario_pool_excludes_previous_unfinished_plan_day():
    data = synthetic_data()
    load_pred = np.full((8, 144), 1000.0)
    pv_pred = np.zeros((8, 144))
    load, _, _ = _recency_scenarios(
        data, load_pred, pv_pred, day=7, count=20, window=60, gamma=0.0
    )
    residual_first_slots = load[:, 0] - load_pred[7, 0]
    assert data.load[6, 0] - load_pred[6, 0] not in residual_first_slots
    assert data.load[5, 0] - load_pred[5, 0] in residual_first_slots


def test_pending_energy_projection_is_physical():
    charged = project_pending_energy(6000.0, 200.0, 600.0, 0.0)
    discharged = project_pending_energy(6000.0, 0.0, 1200.0, 0.0)
    assert 6000.0 < charged <= 10800.0
    assert 1200.0 <= discharged < 6000.0


def test_battery_b_pending_projection_uses_frozen_action():
    no_action = project_planned_pending_energy(
        6000.0, 300.0, 600.0, 0.0, 0.0, 0.0
    )
    frozen_charge = project_planned_pending_energy(
        6000.0, 300.0, 600.0, 0.0, 100.0, 0.0
    )
    assert no_action == 6000.0
    assert frozen_charge == 6090.0


def test_candidate_scores_are_released_only_after_two_plan_days():
    histories = {"a": [], "b": []}
    pending = [(0, {"a": 1.0, "b": 2.0}), (1, {"a": 3.0, "b": 4.0})]
    pending = release_mature_scores(pending, histories, day=1)
    assert histories == {"a": [], "b": []}
    pending = release_mature_scores(pending, histories, day=2)
    assert histories == {"a": [1.0], "b": [2.0]}
    assert pending == [(1, {"a": 3.0, "b": 4.0})]


def test_candidate_grid_matches_frozen_online_selector():
    candidates = candidate_grid()
    assert len(candidates) == 15
    assert len({item["candidate_id"] for item in candidates}) == 15
    assert any(item["candidate_id"] == "cvar_t0.90_r0.05_g0.00" for item in candidates)


def test_one_slot_delayed_controller_cannot_react_to_current_actual():
    grid = np.full(4, 100.0)
    forecast = np.full(4, 600.0)
    pv = np.zeros(4)
    base_load = np.full(4, 600.0)
    base_load[3] = 1200.0
    changed_load = base_load.copy()
    changed_load[2] = 1800.0
    base = settle_one_slot_delayed(grid, base_load, pv, forecast, pv, 6000.0)
    changed = settle_one_slot_delayed(grid, changed_load, pv, forecast, pv, 6000.0)
    assert changed["d"][2] == base["d"][2]
    assert changed["commanded_d"][2] == base["commanded_d"][2]
    assert changed["emergency"][2] > base["emergency"][2]
    assert changed["d"][3] > base["d"][3]


def test_one_slot_delay_uses_previous_plan_day_final_measurement():
    grid = np.array([100.0, 100.0])
    load = np.array([1200.0, 600.0])
    pv = np.zeros(2)
    forecast = np.full(2, 600.0)
    without_bridge = settle_one_slot_delayed(
        grid, load, pv, forecast, pv, 6000.0
    )
    with_bridge = settle_one_slot_delayed(
        grid,
        load,
        pv,
        forecast,
        pv,
        6000.0,
        previous_load_kw=1200.0,
        previous_pv_kw=0.0,
    )
    assert without_bridge["d"][0] == 0.0
    assert with_bridge["d"][0] == 100.0
    assert with_bridge["emergency"][0] == 0.0


def test_delayed_pending_projection_uses_previous_observation_command():
    delayed = project_delayed_pending_energy(
        6000.0,
        grid_kwh=0.0,
        observed_load_kw=0.0,
        observed_pv_kw=0.0,
        pending_load_forecast_kw=600.0,
        pending_pv_forecast_kw=0.0,
    )
    immediate = project_pending_energy(6000.0, 0.0, 600.0, 0.0)
    assert delayed == 6000.0
    assert immediate < delayed


def test_delayed_command_is_separate_from_real_time_protection_clip():
    grid = np.array([100.0])
    forecast_load = np.array([1200.0])
    pv = np.zeros(1)
    low_deficit = settle_one_slot_delayed(
        grid, np.array([720.0]), pv, forecast_load, pv, 6000.0
    )
    high_deficit = settle_one_slot_delayed(
        grid, np.array([1200.0]), pv, forecast_load, pv, 6000.0
    )
    assert low_deficit["commanded_d"][0] == high_deficit["commanded_d"][0] == 100.0
    assert low_deficit["d"][0] == 20.0
    assert high_deficit["d"][0] == 100.0
