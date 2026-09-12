import json
from types import SimpleNamespace

import numpy as np
import pandas as pd

from forecasting import forecast_value
from forecasting.experiment import metric_row


def test_interval_metrics_distinguish_requests_labels_and_intervals():
    frame = pd.DataFrame({"prediction": [10., 10., 10.], "target": [10., 20., np.nan],
                          "lower": [8., np.nan, 8.], "upper": [12., np.nan, 12.]})
    result = metric_row(frame)
    assert result["n_requests"] == 3
    assert result["n_scored"] == 2
    assert result["n_intervals"] == 1
    assert result["interval_valid_fraction"] == .5
    assert result["interval_coverage"] == 1.
    assert result["interval_score"] == 4.


def test_forecast_value_replays_csv_contract_without_labels_in_prediction_trace(monkeypatch, tmp_path):
    dates = pd.date_range("2025-02-01", periods=2)
    load = pd.DataFrame(np.full((2, 144), 1000.), index=dates)
    pv = pd.DataFrame(np.zeros((2, 144)), index=dates)
    price = pd.DataFrame(np.ones((2, 144)), index=dates)
    monkeypatch.setattr(forecast_value, "load_problem_data", lambda _: SimpleNamespace(load=load, pv_actual=pv, price=price))
    monkeypatch.setattr(pd, "read_excel", lambda _: pd.DataFrame({"电价": np.ones(144)}))
    rows = []
    names = {"load_10min": "selected_load", "price_10min": "selected_price", "pv_hourly": "selected_pv"}
    baseline = {"load_10min": "seasonal_naive", "price_10min": "seasonal_naive", "pv_hourly": "raw_official"}
    for target, selected in names.items():
        for model in (selected, baseline[target]):
            for date in dates:
                for slot in range(24 if target == "pv_hourly" else 144):
                    offset = pd.Timedelta(hours=slot + 1) if target == "pv_hourly" else pd.Timedelta(minutes=(slot + 1) * 10)
                    rows.append(dict(target_name=target, model=model, issue_time=date,
                                     target_time=date + offset, completed_at=date + offset + pd.Timedelta(minutes=10),
                                     prediction=0. if target == "pv_hourly" else (1. if target == "price_10min" else 1000.),
                                     split="development" if date == dates[0] else "audit"))
    for folder in ("predictions", "reports", "artifacts"):
        (tmp_path / folder).mkdir()
    pd.DataFrame(rows).to_csv(tmp_path / "predictions/candidate_predictions.csv", index=False)
    (tmp_path / "artifacts/selected_models.json").write_text(json.dumps(names))
    cfg = dict(first_forecast_date="2025-02-01", last_forecast_date="2025-02-02",
               development_end="2025-02-01", seed=1)
    result = forecast_value.run_forecast_value(tmp_path, tmp_path, cfg)
    assert set(result["development_selections"]) == {"fixed_price_proxy", "variable_price_proxy"}
    summary = pd.read_csv(tmp_path / "reports/forecast_value_summary.csv")
    assert np.isfinite(summary.cash_cost).all()
    for _, group in summary.groupby(["scenario", "split"]):
        np.testing.assert_allclose(group.cash_cost, group.cash_cost.iloc[0])
    trace = pd.read_csv(tmp_path / "predictions/load_10min_adaptation.csv")
    assert {"target", "actual", "base_error"}.isdisjoint(trace)
