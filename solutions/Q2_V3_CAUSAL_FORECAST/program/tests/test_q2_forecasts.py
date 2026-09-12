from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import q2_forecasts
from q2_forecasts import (
    ARM_MODEL_IDS,
    ForecastBundle,
    HGB_PARAMETERS,
    build_b0_forecasts,
    build_daily_features,
    shift_cross_day,
)
from q2_model import load_data


def test_forecast_arm_ids_are_unique_and_frozen():
    assert list(ARM_MODEL_IDS) == ["B0", "B1", "Abl-L", "Abl-PV"]
    assert len(set(ARM_MODEL_IDS.values())) == 4
    assert HGB_PARAMETERS["random_state"] == 20260912
    assert HGB_PARAMETERS["early_stopping"] is False


def test_q2_forecast_program_has_no_attachment3_path():
    source = Path(q2_forecasts.__file__).read_text(encoding="utf-8")
    assert "附件3" not in source
    assert "pv_forecasts" not in source


def test_cross_day_mapping_does_not_wrap_each_day():
    values = np.arange(3 * 144, dtype=float).reshape(3, 144)
    shifted = shift_cross_day(values)
    np.testing.assert_array_equal(shifted[0, :-1], values[0, 1:])
    assert shifted[0, -1] == values[1, 0]
    assert shifted[1, -1] == values[2, 0]
    assert np.isnan(shifted[2, -1])


def test_midnight_pending_interval_is_not_a_lag1_feature():
    dates = pd.date_range("2025-01-01", periods=35)
    values = np.arange(35 * 144, dtype=float).reshape(35, 144)
    frame = build_daily_features(values, dates)
    row = frame[(frame.date == pd.Timestamp("2025-02-01")) & (frame.slot == 143)].iloc[0]
    assert np.isnan(row["lag_1d"])
    expected = np.mean(values[16:30, 143])
    assert np.isclose(row["rolling_mean_14d"], expected)
    assert row["completed_at"] == pd.Timestamp("2025-02-02 00:10")


def test_january_cold_start_is_exact_and_finite():
    data = load_data()
    load, pv = build_b0_forecasts(data)
    typical = pd.read_excel(q2_forecasts.ATTACHMENT1)
    np.testing.assert_allclose(load[0], typical.iloc[:, 2].to_numpy(float))
    np.testing.assert_allclose(load[7], data.load[0])
    np.testing.assert_allclose(load[14], (data.load[7] + data.load[0]) / 2)
    np.testing.assert_allclose(pv[0], typical.iloc[:, 3].to_numpy(float))
    np.testing.assert_allclose(pv[5], data.pv[:5].mean(axis=0))
    assert np.isfinite(load).all()
    assert np.isfinite(pv).all()


def test_all_arms_share_the_same_january_forecasts():
    base_load = np.ones((365, 144))
    base_pv = np.ones((365, 144)) * 2
    hgb_load = base_load.copy()
    hgb_pv = base_pv.copy()
    hgb_load[31:] = 3
    hgb_pv[31:] = 4
    bundle = ForecastBundle(
        base_load, base_pv, hgb_load, hgb_pv, pd.DataFrame()
    )
    forecasts = [bundle.for_arm(arm) for arm in ARM_MODEL_IDS]
    for load, pv in forecasts:
        np.testing.assert_array_equal(load[:31], base_load[:31])
        np.testing.assert_array_equal(pv[:31], base_pv[:31])
