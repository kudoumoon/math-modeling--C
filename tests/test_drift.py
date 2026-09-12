import numpy as np
import pandas as pd

from forecasting.drift import DriftConfig, adapt_daily_forecasts


def test_drift_adapter_never_uses_current_day_residual():
    dates = pd.date_range("2025-01-01", periods=12, freq="D")
    rows = []
    actual_rows = []
    for i, date in enumerate(dates):
        for slot in range(4):
            issue = date
            target = date + pd.Timedelta(minutes=10 * (slot + 1))
            pred = 100.0
            actual = pred + (20.0 if i >= 8 else 0.0)
            rows.append((issue, target, pred))
            actual_rows.append((target, actual))
    forecasts = pd.DataFrame(rows, columns=["issue_time", "target_time", "prediction"])
    actual = pd.DataFrame(actual_rows, columns=["target_time", "actual"])
    result = adapt_daily_forecasts(forecasts, actual, DriftConfig())
    current = result[result.issue_time == dates[8]]
    assert np.allclose(current.online_correction, 0.0)
    later = result[result.issue_time == dates[11]]
    assert np.all(later.drift_score.to_numpy() >= 0)
    assert np.all(later.online_correction.to_numpy() > 0)
