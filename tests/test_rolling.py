import numpy as np
import pandas as pd

from forecasting.rolling_backtest import _bootstrap_mean, _economic_gate, _issue_pv_day


def test_pv_issue_mapping_uses_six_ten_minute_intervals():
    issue = pd.Timestamp("2025-02-01 06:00")
    lookup = {(issue, issue + pd.Timedelta(minutes=10) + pd.Timedelta(hours=h) + pd.Timedelta(minutes=j * 10)): float(h + 1)
              for h in range(24) for j in range(6)}
    day = _issue_pv_day(pd.Timestamp("2025-02-01"), 6, lookup)
    assert np.isclose(day[36], 1.0)
    assert np.isclose(day[41], 1.0)
    assert np.isclose(day[42], 2.0)
    assert np.isnan(day[35])


def test_block_bootstrap_returns_finite_interval():
    result = _bootstrap_mean(np.arange(20, dtype=float), block=3, n_boot=200, seed=1)
    assert result["lower_95"] <= result["mean"] <= result["upper_95"]


def test_economic_gate_rejects_fee_dominated_update():
    idx = pd.date_range("2025-01-01", periods=30, freq="D")
    date = idx[-1]
    pred = pd.DataFrame(np.zeros((30, 144)), index=idx)
    residual = pd.DataFrame(np.zeros((30, 144)), index=idx)
    q0 = np.ones(144)
    candidate = q0.copy(); candidate[:6] += 100.0
    prices = pd.DataFrame(np.ones((30, 144)), index=idx)
    allowed, expected, downside = _economic_gate(
        date, 29, np.r_[np.ones(6, dtype=bool), np.zeros(138, dtype=bool)],
        q0, candidate, pred, residual, prices, min_history=14
    )
    assert not allowed
    assert expected < 0 and downside < 0
