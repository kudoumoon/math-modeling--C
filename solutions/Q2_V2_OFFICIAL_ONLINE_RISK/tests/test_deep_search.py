import numpy as np

from q2_deep_core import (
    weighted_quantile,
    s2_load_forecast,
    s2_pv_forecast,
    recency_weights,
    select_day_type_candidates,
)


def test_weighted_quantile_respects_heavy_recent_weight():
    values = np.array([0.0, 1.0, 10.0])
    weights = np.array([0.05, 0.05, 0.90])
    assert weighted_quantile(values, 0.8, weights) == 10.0


def test_s2_load_forecast_uses_only_past_same_weekdays():
    load = np.arange(40 * 3, dtype=float).reshape(40, 3)
    pred = s2_load_forecast(load)
    day = 35
    base = load[[28, 21, 14, 7]].mean(axis=0)
    last_mean = load[28].mean()
    ref_mean = load[[28, 21, 14, 7]].mean()
    correction = np.clip((last_mean - ref_mean) / 2.0, -0.2 * ref_mean, 0.2 * ref_mean)
    np.testing.assert_allclose(pred[day], np.maximum(base + correction, 0.0))


def test_s2_pv_forecast_exact_half_fusion():
    pv = np.arange(12 * 2, dtype=float).reshape(12, 2)
    pred = s2_pv_forecast(pv, recent_days=7, yesterday_weight=0.5)
    np.testing.assert_allclose(pred[8], 0.5 * pv[7] + 0.5 * pv[1:8].mean(axis=0))


def test_recency_weights_are_normalized_and_recent_is_larger():
    w = recency_weights(np.array([5, 6, 7]), day=8, gamma=0.1)
    assert np.isclose(w.sum(), 1.0)
    assert w[-1] > w[0]


def test_day_type_candidates_never_include_current_or_future_day():
    dates = np.datetime64("2025-01-01") + np.arange(100).astype("timedelta64[D]")
    pv_total = np.linspace(0, 1, 100)
    load_total = np.linspace(1, 0, 100)
    chosen = select_day_type_candidates(dates, 70, 60, pv_total, load_total)
    assert np.all(chosen < 70)
