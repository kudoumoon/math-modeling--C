import numpy as np
import pandas as pd

from forecasting.data import _attach_hourly_pv_actual, _read_pv_forecasts
from forecasting.rolling_backtest import _pv_issue_lookup


def test_shifted_hour_labels_mapping_and_energy_are_consistent(monkeypatch):
    raw = pd.DataFrame({"日期": [pd.Timestamp("2025-01-01")] * 2,
                        "预报时刻": ["0:00", "18:00"],
                        **{f"预报{i}小时": [60.0, 60.0] for i in range(1, 25)}})
    monkeypatch.setattr(pd, "read_excel", lambda *_: raw.copy())
    forecasts = _read_pv_forecasts("unused.xlsx")
    actual = pd.DataFrame(np.zeros((3, 144)), index=pd.date_range("2025-01-01", periods=3))
    actual.iloc[0, :6] = [10, 20, 30, 40, 50, 60]
    actual.iloc[0, 138:144] = [1, 2, 3, 4, 5, 6]
    attached = _attach_hourly_pv_actual(forecasts, actual)
    first = attached.iloc[0]
    assert first.window_start == pd.Timestamp("2025-01-01 00:10")
    assert first.window_end == pd.Timestamp("2025-01-01 01:10")
    assert first.actual_pv == 35
    midnight = attached[(attached.issue_hour == 0) & (attached.lead_hour == 24)].iloc[0]
    assert midnight.actual_pv == 3.5
    assert midnight.window_end == pd.Timestamp("2025-01-02 00:10")
    next_day = attached[(attached.issue_hour == 18) & (attached.lead_hour == 7)].iloc[0]
    assert next_day.window_start == pd.Timestamp("2025-01-02 00:10")
    forecasts["target_name"] = "pv_hourly"
    forecasts["prediction"] = forecasts.raw_pv
    lookup = _pv_issue_lookup(forecasts)
    issue = pd.Timestamp("2025-01-01")
    starts = pd.date_range("2025-01-01 00:10", periods=6, freq="10min")
    assert sum(lookup[(issue, t)] / 6 for t in starts) == 60
    assert (issue, pd.Timestamp("2025-01-01 00:00")) not in lookup
