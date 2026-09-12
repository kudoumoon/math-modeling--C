from io import StringIO

import numpy as np
import pandas as pd
import pytest

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


def test_drift_completion_boundary_and_future_perturbation():
    dates = pd.date_range("2025-01-01", periods=5)
    rows = [(date, date + pd.Timedelta(minutes=(slot + 1) * 10), 0.)
            for date in dates for slot in (0, 142, 143)]
    forecasts = pd.DataFrame(rows, columns=["issue_time", "target_time", "prediction"])
    actual = forecasts[["target_time"]].copy()
    actual["actual"] = np.repeat(np.arange(1., 6.), 3)
    cfg = DriftConfig(long_window_days=1, short_window_days=1, min_history_days=1)
    baseline = adapt_daily_forecasts(forecasts, actual, cfg)
    cutoff = dates[3]
    current = baseline[baseline.issue_time == cutoff].set_index("slot")
    assert current.loc[0, "online_correction"] == 3.
    assert current.loc[142, "online_correction"] == 3.
    assert current.loc[143, "online_correction"] == 2.
    actual.loc[actual.target_time + pd.Timedelta(minutes=10) > cutoff, "actual"] = 1e9
    changed = adapt_daily_forecasts(forecasts, actual, cfg)
    columns = ["online_correction", "adaptive_prediction", "drift_score"]
    pd.testing.assert_frame_equal(baseline.loc[baseline.issue_time <= cutoff, columns],
                                  changed.loc[changed.issue_time <= cutoff, columns])


def test_drift_uses_completed_history_across_missing_issue_day():
    dates = pd.to_datetime(["2025-01-01", "2025-01-03"])
    forecasts = pd.DataFrame({"issue_time": dates, "target_time": dates + pd.Timedelta(days=1),
                              "prediction": 0.})
    actual = pd.DataFrame({"target_time": forecasts.target_time, "actual": [7., 100.]})
    cfg = DriftConfig(long_window_days=1, short_window_days=1, min_history_days=1)
    result = adapt_daily_forecasts(forecasts, actual, cfg)
    assert result.iloc[1].online_correction == 7.


@pytest.mark.parametrize("parse_dates", [False, ["issue_time", "target_time"]])
@pytest.mark.parametrize("with_completion", [False, True])
def test_drift_csv_roundtrip_matches_datetime_input(parse_dates, with_completion):
    dates = pd.date_range("2025-01-01", periods=5)
    rows = [(date, date + pd.Timedelta(minutes=(slot + 1) * 10), 0.)
            for date in dates for slot in (0, 142, 143)]
    forecasts = pd.DataFrame(rows, columns=["issue_time", "target_time", "prediction"])
    if with_completion:
        forecasts["completed_at"] = forecasts.target_time + pd.Timedelta(minutes=10)
    actual = pd.DataFrame({"target_time": forecasts.target_time,
                           "actual": np.repeat(np.arange(1., 6.), 3)})
    cfg = DriftConfig(long_window_days=1, short_window_days=1, min_history_days=1)
    expected = adapt_daily_forecasts(forecasts, actual, cfg)
    restored = pd.read_csv(StringIO(forecasts.to_csv(index=False)), parse_dates=parse_dates)
    restored_actual = pd.read_csv(StringIO(actual.to_csv(index=False)))
    before = restored.copy(deep=True)
    before_actual = restored_actual.copy(deep=True)
    result = adapt_daily_forecasts(restored, restored_actual, cfg)
    pd.testing.assert_frame_equal(result, expected)
    pd.testing.assert_frame_equal(restored, before)
    pd.testing.assert_frame_equal(restored_actual, before_actual)
    # The previous day's last slot remains unavailable after CSV reloading.
    current = result[result.issue_time == dates[3]].set_index("slot")
    assert current.loc[142, "online_correction"] == 3.
    assert current.loc[143, "online_correction"] == 2.
