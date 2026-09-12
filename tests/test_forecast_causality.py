import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyRegressor
import joblib

from forecasting import backtest
from forecasting.features import build_daily_features, build_pv_calibration_features, feature_columns
from forecasting.models import make_models


def _matrix():
    return pd.DataFrame(np.arange(40 * 144, dtype=float).reshape(40, 144),
                        index=pd.date_range("2025-01-01", periods=40))


def _cfg(**overrides):
    return dict(first_forecast_date="2025-02-01", last_forecast_date="2025-02-01",
                development_end="2025-06-30", seed=1, hist_gradient_boosting={},
                interval_coverage=0.9, residual_window_days=28, **overrides)


@pytest.mark.parametrize("target", ["load_10min", "price_10min"])
def test_monthly_training_uses_only_completed_labels(monkeypatch, target):
    monkeypatch.setattr(backtest, "make_models", lambda *args: [
        SimpleNamespace(name="mean", estimator=DummyRegressor())])
    values = _matrix()
    cutoff = pd.Timestamp("2025-02-01")
    base = backtest._daily_candidate_predictions(values, target, _cfg())
    changed = values.copy()
    changed.loc[cutoff:] = 1e9
    changed.loc["2025-01-31", 143] = 1e9
    other = backtest._daily_candidate_predictions(changed, target, _cfg())
    np.testing.assert_allclose(base.prediction, other.prediction)
    # Slot 142 ends exactly at cutoff and must remain in the training set.
    assert base.prediction.iloc[0] == pytest.approx(values.loc[:"2025-01-31"].to_numpy().ravel()[:-1].mean())
    assert base.completed_at.iloc[-1] == cutoff + pd.Timedelta(days=1, minutes=10)


def test_feature_future_perturbation_and_available_last_slot_history():
    values = _matrix()
    cutoff = pd.Timestamp("2025-02-01")
    changed = values.copy()
    changed.loc[cutoff:] = 1e9
    changed.loc["2025-01-31", 143] = 1e9
    base = build_daily_features(values)
    other = build_daily_features(changed)
    columns = feature_columns(base)
    pd.testing.assert_frame_equal(base.loc[base.date <= cutoff, columns],
                                  other.loc[other.date <= cutoff, columns])
    last = base[(base.date == cutoff) & (base.slot == 143)].iloc[0]
    assert np.isnan(last.lag_1d)
    assert last.lag_7d == values.loc["2025-01-25", 143]
    assert last.rolling_mean_3d == values.loc["2025-01-28":"2025-01-30", 143].mean()
    assert last.same_weekday_mean_4 == values.loc[pd.to_datetime([
        "2025-01-04", "2025-01-11", "2025-01-18", "2025-01-25"]), 143].mean()


@pytest.mark.parametrize("explicit_completion", [False, True])
def test_intervals_use_completion_not_target_time(explicit_completion):
    cutoff = pd.Timestamp("2025-02-01")
    history = pd.DataFrame({
        "target_name": "pv_hourly", "model": "raw_official",
        "issue_time": [cutoff - pd.Timedelta(days=1)] * 32,
        "target_time": [cutoff - pd.Timedelta(minutes=20)] * 30
                       + [cutoff - pd.Timedelta(minutes=10), cutoff - pd.Timedelta(minutes=5)],
        "prediction": 10., "target": [11.] * 30 + [20., 1e8],
    })
    current = history.iloc[[0]].copy()
    current["issue_time"] = cutoff
    current["target_time"] = cutoff + pd.Timedelta(hours=1)
    frame = pd.concat([history, current], ignore_index=True)
    if explicit_completion:
        frame["completed_at"] = frame.target_time + pd.Timedelta(minutes=10)
        frame.loc[30, "target_time"] = cutoff - pd.Timedelta(minutes=5)
        frame.loc[31, "target_time"] = cutoff - pd.Timedelta(minutes=10)
    out = backtest._causal_intervals(frame, 1., 28)
    assert out.iloc[-1].upper == 20.
    changed = frame.copy()
    completion = (changed.completed_at if explicit_completion
                  else changed.target_time + pd.Timedelta(minutes=10))
    changed.loc[completion > cutoff, "target"] = -1e12
    other = backtest._causal_intervals(changed, 1., 28)
    pd.testing.assert_frame_equal(out[["lower", "upper"]], other[["lower", "upper"]])


def test_pv_keeps_unlabeled_year_end_predictions_and_filters_training(monkeypatch, tmp_path):
    monkeypatch.setattr(backtest, "make_models", lambda *args: [
        SimpleNamespace(name="mean", estimator=DummyRegressor())])
    issues = pd.to_datetime(["2025-11-01 00:00", "2025-11-02 00:00", "2025-11-30 23:00", "2025-12-31 18:00"])
    frame = pd.DataFrame({"issue_time": issues, "lead_hour": 24,
                          "issue_hour": issues.hour, "raw_pv": 10.,
                          "actual_pv": [12., np.nan, 1e9, np.nan]})
    frame["target_time"] = frame.issue_time + pd.Timedelta(hours=24)
    frame["window_end"] = frame.target_time + pd.Timedelta(minutes=10)
    cfg = _cfg()
    cfg.update(first_forecast_date="2025-12-01", last_forecast_date="2025-12-31")
    result = backtest._pv_candidate_predictions(SimpleNamespace(pv_forecasts=frame), cfg, tmp_path)
    assert len(result) == 2
    assert result.target.isna().all()
    assert result.loc[result.model == "mean_residual", "prediction"].iloc[0] == 12.
    assert result.completed_at.eq(pd.Timestamp("2026-01-01 18:10")).all()
    metrics = backtest._metrics(result)
    assert metrics.n.eq(0).all()
    assert metrics.n_predictions.eq(1).all()
    assert metrics.n_missing_actual.eq(1).all()
    assert metrics.mae.isna().all()
    saved = joblib.load(tmp_path / "models/pv_hourly/2025-12/mean_residual.joblib")
    test = build_pv_calibration_features(frame.iloc[[-1]])
    restored = np.clip(test.raw_pv.to_numpy() + saved["estimator"].predict(test[saved["feature_columns"]]), 0, None)
    np.testing.assert_allclose(restored, result.loc[result.model == "mean_residual", "prediction"])
    assert saved["predicts_residual"]
    assert saved["train_end"] == pd.Timestamp("2025-11-02 00:10")


def test_selection_ignores_audit_and_missing_labels():
    frame = pd.DataFrame({"target_name": "load_10min", "model": ["a", "b", "a", "b", "a"],
                          "split": ["development"] * 2 + ["audit"] * 2 + ["development"],
                          "target": [0., 0., 0., 0., np.nan], "prediction": [1., 2., 1e9, 0., 1e9]})
    assert backtest._select_on_development(frame) == {"load_10min": "a"}


def test_all_96_year_end_pv_forecasts_survive_36_missing_labels(monkeypatch):
    monkeypatch.setattr(backtest, "make_models", lambda *args: [])
    issues = pd.date_range("2025-12-31", periods=4, freq="6h")
    frame = pd.DataFrame({"issue_time": np.repeat(issues, 24),
                          "lead_hour": np.tile(np.arange(1, 25), 4), "raw_pv": 10.})
    frame["issue_hour"] = frame.issue_time.dt.hour
    frame["target_time"] = frame.issue_time + pd.to_timedelta(frame.lead_hour, unit="h")
    frame["window_end"] = frame.target_time + pd.Timedelta(minutes=10)
    frame["actual_pv"] = np.where(frame.window_end <= pd.Timestamp("2026-01-01 00:10"), 11., np.nan)
    cfg = _cfg()
    cfg.update(first_forecast_date="2025-12-31", last_forecast_date="2025-12-31")
    result = backtest._pv_candidate_predictions(SimpleNamespace(pv_forecasts=frame), cfg)
    assert len(result) == 96
    assert result.groupby("issue_hour").size().eq(24).all()
    assert result.target.isna().sum() == 36
    metric = backtest._metrics(result).iloc[0]
    assert metric.n == 60
    assert metric.n_missing_actual == 36
    assert metric.mae == 1.


def test_output_root_isolates_outputs_and_labels(monkeypatch, tmp_path):
    root = tmp_path / "input"
    root.mkdir()
    (root / "config.json").write_text(json.dumps(_cfg()))
    def load_data(path):
        assert path == root
        return SimpleNamespace(load=None, price=None)
    monkeypatch.setattr(backtest, "load_problem_data", load_data)
    def candidate(target):
        return pd.DataFrame({"target_name": [target], "model": ["a"],
                             "issue_time": pd.to_datetime(["2025-02-01"]),
                             "target_time": pd.to_datetime(["2025-02-01 01:00"]),
                             "completed_at": pd.to_datetime(["2025-02-01 01:10"]),
                             "lead_hour": [1], "issue_hour": [0], "target": [12.],
                             "prediction": [10.], "split": ["development"], "train_end": ["2025-01-31"]})
    monkeypatch.setattr(backtest, "_daily_candidate_predictions", lambda _, target, cfg, **kwargs: candidate(target))
    monkeypatch.setattr(backtest, "_pv_candidate_predictions", lambda *args, **kwargs: candidate("pv_hourly"))
    output = tmp_path / "experiments" / "first"
    backtest.run_backtest(root, "config.json", output_root=output)
    assert sorted(p.name for p in root.iterdir()) == ["config.json"]
    detail = pd.read_csv(output / "predictions/candidate_predictions.csv")
    selected = pd.read_csv(output / "predictions/causal_forecasts.csv")
    assert {"target", "lead_hour", "issue_hour", "completed_at"} <= set(detail)
    assert {"target", "actual_pv", "actual"}.isdisjoint(selected)
    assert len(detail) == len(selected) == 3


def test_metric_coverage_excludes_unobserved_labels():
    frame = pd.DataFrame({"target_name": "pv_hourly", "model": "a", "split": "audit",
                          "target": [10., np.nan], "prediction": [11., 11.],
                          "lower": [9., 9.], "upper": [12., 12.]})
    metric = backtest._metrics(frame).iloc[0]
    assert metric.n == metric.n_intervals == metric.n_missing_actual == 1
    assert metric.n_predictions == 2
    assert metric.interval_coverage == 1.


@pytest.mark.parametrize("names", [[], ["invalid"], ["ridge", "ridge"], "ridge", [None]])
def test_invalid_model_configuration_is_rejected(names):
    with pytest.raises(ValueError, match="models must"):
        make_models(1, {}, names)


@pytest.mark.parametrize("name", ["ridge", "seasonal_naive"])
def test_cold_start_fails_explicitly(name):
    cfg = _cfg()
    cfg.update(models=[name], first_forecast_date="2025-01-01", last_forecast_date="2025-01-01")
    with pytest.raises(ValueError, match="completed"):
        backtest._daily_candidate_predictions(_matrix(), "load_10min", cfg)


def test_configured_model_reload_matches_point_predictions(tmp_path):
    cfg = _cfg(models=["ridge"])
    values = _matrix()
    result = backtest._daily_candidate_predictions(values, "load_10min", cfg, tmp_path)
    assert result.model.unique().tolist() == ["ridge"]
    path = tmp_path / "models/load_10min/2025-02/ridge.joblib"
    saved = joblib.load(path)
    features = build_daily_features(values)
    test = features[features.date == pd.Timestamp("2025-02-01")]
    restored = np.clip(saved["estimator"].predict(test[saved["feature_columns"]]), 0, None)
    np.testing.assert_allclose(restored, result.prediction, rtol=0, atol=0)
    assert json.loads(path.with_suffix(".features.json").read_text()) == saved["feature_columns"]
    assert saved["train_end"] == pd.Timestamp("2025-02-01")
    assert result.train_end.eq(saved["train_end"]).all()
    assert result.interval_start.equals(result.target_time)
    assert result.interval_end.equals(result.completed_at)
    assert result.unit.eq("kW").all()


def test_naive_has_no_fit_timestamp_and_price_unit():
    result = backtest._daily_candidate_predictions(_matrix(), "price_10min", _cfg(models=["seasonal_naive"]))
    assert result.train_end.isna().all()
    assert result.history_cutoff.eq(result.issue_time).all()
    assert result.unit.eq("yuan/kWh").all()
