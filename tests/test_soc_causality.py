from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from forecasting import economic_backtest, rolling_backtest
from forecasting.economic import E_MIN, E_MAX, execute_day, project_interval_energy


def _run(monkeypatch, path, load, pv, net=None):
    dates = load.index
    zeros = load * 0.
    net = zeros if net is None else net
    seen = []
    def planner(forecast, price, energy):
        seen.append((forecast.copy(), price.copy(), energy))
        return np.zeros(144)
    if path == "daily":
        monkeypatch.setattr(economic_backtest, "plan_day", planner)
        result = economic_backtest._simulate(dates, net, zeros, zeros + 1., zeros + 1., load, pv)
    else:
        monkeypatch.setattr(rolling_backtest, "plan_day", planner)
        result = rolling_backtest._simulate_policy(
            SimpleNamespace(load=load, pv_actual=pv), dates, net,
            {date: np.zeros(144) for date in dates}, False,
            zeros + 1., zeros + 1., .7, False, {})
    return result, seen


@pytest.mark.parametrize("path", ["daily", "rolling"])
@pytest.mark.parametrize("source", ["load", "pv"])
def test_pending_final_actual_cannot_change_next_midnight_plan(monkeypatch, path, source):
    zeros = pd.DataFrame(np.zeros((3, 144)), index=pd.date_range("2025-02-01", periods=3))
    base, original = _run(monkeypatch, path, zeros, zeros)
    changed = zeros.copy()
    changed.iloc[0, 143] = 600.
    load, pv = (changed, zeros) if source == "load" else (zeros, changed)
    result, seen = _run(monkeypatch, path, load, pv)
    for old, new in zip(original[:2], seen[:2]):
        np.testing.assert_array_equal(old[0], new[0])
        np.testing.assert_array_equal(old[1], new[1])
        assert old[2] == new[2]
    assert result.iloc[0].end_energy_kwh != base.iloc[0].end_energy_kwh
    assert result.iloc[0].energy_before_final == 6000.
    assert result.iloc[1].estimated_initial_energy_kwh == 6000.
    # Execution starts from actual prior end state, never the planning estimate.
    np.testing.assert_array_equal(result.actual_initial_energy_kwh.iloc[1:].to_numpy(),
                                  result.end_energy_kwh.iloc[:-1].to_numpy())
    assert result.iloc[1].actual_initial_energy_kwh != result.iloc[1].estimated_initial_energy_kwh
    assert result.iloc[1].end_energy_kwh == result.iloc[0].end_energy_kwh
    # By the following midnight this perturbation has become observed history.
    assert seen[2][2] != original[2][2]


@pytest.mark.parametrize("path", ["daily", "rolling"])
@pytest.mark.parametrize("source", ["load", "pv"])
def test_completed_slot_142_changes_next_midnight_plan(monkeypatch, path, source):
    zeros = pd.DataFrame(np.zeros((2, 144)), index=pd.date_range("2025-02-01", periods=2))
    changed = zeros.copy()
    changed.iloc[0, 142] = 600.
    load, pv = (changed, zeros) if source == "load" else (zeros, changed)
    result, seen = _run(monkeypatch, path, load, pv)
    assert seen[1][2] != 6000.
    assert seen[1][2] == result.iloc[0].energy_before_final


@pytest.mark.parametrize("energy,purchase,net", [
    (6000., 100., 0.), (6000., 0., 600.), (E_MIN, 0., 600.),
    (E_MAX, 100., 0.), (6000., 10000., 0.), (6000., 0., 60000.),
])
def test_single_interval_projection_matches_executor(energy, purchase, net):
    q = np.zeros(144)
    load = np.zeros(144)
    q[-1] = purchase
    load[-1] = net
    result = execute_day(q, load, np.zeros(144), np.ones(144), energy)
    assert result.energy_before_final == energy
    assert project_interval_energy(energy, purchase, net) == result.end_energy


@pytest.mark.parametrize("path", ["daily", "rolling"])
def test_pending_projection_uses_issued_net_forecast(monkeypatch, path):
    zeros = pd.DataFrame(np.zeros((2, 144)), index=pd.date_range("2025-02-01", periods=2))
    forecast = zeros.copy()
    forecast.iloc[0, 143] = 600.
    result, seen = _run(monkeypatch, path, zeros, zeros, forecast)
    assert seen[1][2] == project_interval_energy(6000., 0., 600.)
    assert result.iloc[1].actual_initial_energy_kwh == 6000.


def test_rolling_projection_uses_confirmed_final_purchase_and_latest_release(monkeypatch):
    dates = pd.date_range("2025-02-01", periods=2)
    zeros = pd.DataFrame(np.zeros((2, 144)), index=dates)
    seen = []
    def planner(net, price, energy):
        seen.append(energy)
        return np.zeros(144)
    monkeypatch.setattr(rolling_backtest, "plan_day", planner)
    monkeypatch.setattr(rolling_backtest, "_economic_gate", lambda *args: (True, 1., 1.))
    def release(date, hour, lookup):
        values = np.full(144, np.nan)
        if date == dates[0] and hour == 18:
            values[-1] = 300.
        return values
    monkeypatch.setattr(rolling_backtest, "_issue_pv_day", release)
    forecast = zeros.copy()
    forecast.iloc[0, 143] = 600.
    pv_forecast = {date: np.zeros(144) for date in dates}
    pv_forecast[dates[0]][-1] = 600.
    result = rolling_backtest._simulate_policy(
        SimpleNamespace(load=zeros, pv_actual=zeros), dates, forecast,
        pv_forecast, True, zeros + 1., zeros + 1., .7, True, {})
    assert result.iloc[0].adjustment_up_kwh == 50.
    assert seen[1] == project_interval_energy(6000., 50., 300.)
    assert result.iloc[1].actual_initial_energy_kwh == 6045.
