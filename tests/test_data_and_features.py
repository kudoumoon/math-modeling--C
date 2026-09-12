import numpy as np
import pandas as pd

from forecasting.data import daily_to_long
from forecasting.features import build_daily_features


def _matrix(days=35):
    dates = pd.date_range("2025-01-01", periods=days, freq="D")
    values = np.arange(days * 144, dtype=float).reshape(days, 144)
    return pd.DataFrame(values, index=pd.DatetimeIndex(dates, name="date"), columns=range(144))


def test_daily_time_mapping_is_contiguous_and_keeps_zero_plus_one_at_end():
    long = daily_to_long(_matrix(2), "value")
    assert long.iloc[0]["interval_start"] == pd.Timestamp("2025-01-01 00:10")
    assert long.iloc[143]["interval_start"] == pd.Timestamp("2025-01-02 00:00")
    assert long.iloc[144]["interval_start"] == pd.Timestamp("2025-01-02 00:10")
    assert long["interval_start"].diff().dropna().eq(pd.Timedelta(minutes=10)).all()


def test_all_value_features_are_past_shifted():
    matrix = _matrix()
    features = build_daily_features(matrix)
    row = features[(features["date"] == pd.Timestamp("2025-01-15")) & (features["slot"] == 10)].iloc[0]
    assert row["lag_1d"] == matrix.loc["2025-01-14", 10]
    assert row["lag_7d"] == matrix.loc["2025-01-08", 10]
    assert row["rolling_mean_3d"] == matrix.loc["2025-01-12":"2025-01-14", 10].mean()


def test_unfinished_previous_day_final_interval_is_never_a_feature():
    features = build_daily_features(_matrix())
    last_slot = features[features["slot"] == 143]
    assert last_slot["lag_1d"].isna().all()
    values = _matrix()
    row = last_slot[last_slot["date"] == pd.Timestamp("2025-01-15")].iloc[0]
    assert row["rolling_mean_7d"] == values.loc["2025-01-07":"2025-01-13", 143].mean()
