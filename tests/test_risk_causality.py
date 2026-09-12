import numpy as np
import pandas as pd
from types import SimpleNamespace

from forecasting.economic_backtest import _causal_residual_quantiles
from forecasting import rolling_backtest


def test_first_day_risk_margin_cannot_observe_future_residuals():
    dates = pd.date_range("2025-02-01", periods=20)
    predicted = pd.DataFrame(np.zeros((20, 144)), index=dates)
    actual = predicted.copy()
    actual.iloc[1:, :] = 1000.0
    margin = _causal_residual_quantiles(predicted, actual, 0.7)
    assert np.array_equal(margin.iloc[0].to_numpy(), np.zeros(144))


def test_risk_margin_excludes_unfinished_previous_day_last_interval():
    dates = pd.date_range("2025-02-01", periods=20)
    predicted = pd.DataFrame(np.zeros((20, 144)), index=dates)
    actual = predicted.copy()
    before = _causal_residual_quantiles(predicted, actual, 0.99)
    actual.iloc[9, 143] = 1000.0
    actual.iloc[10:, :] = 2000.0
    after = _causal_residual_quantiles(predicted, actual, 0.99)
    np.testing.assert_array_equal(before.iloc[:11], after.iloc[:11])


def test_rolling_first_day_plan_is_invariant_to_future_actuals(monkeypatch):
    dates = pd.date_range("2025-02-01", periods=20)
    zeros = pd.DataFrame(np.zeros((20, 144)), index=dates)
    data = SimpleNamespace(load=zeros.copy(), pv_actual=zeros.copy())
    captured = []
    def plan(net, price, energy):
        captured.append(net.copy())
        return np.zeros(144)
    monkeypatch.setattr(rolling_backtest, "plan_day", plan)
    monkeypatch.setattr(rolling_backtest, "_execute_contract", lambda *args: {
        "end_energy_kwh": 6000.0, "energy_before_final": 6000.0})
    pv = {d: np.zeros(144) for d in dates}
    rolling_backtest._simulate_policy(data, dates, zeros, pv, False, zeros, zeros, .7, False, {})
    first = captured[0].copy()
    captured.clear()
    data.load.iloc[1:] = 10000.0
    rolling_backtest._simulate_policy(data, dates, zeros, pv, False, zeros, zeros, .7, False, {})
    np.testing.assert_array_equal(first, captured[0])
