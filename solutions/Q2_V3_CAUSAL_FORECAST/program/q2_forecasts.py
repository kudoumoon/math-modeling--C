"""Frozen Q2-only forecasts built from attachments 1 and 2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from q2_model import ATTACHMENT1, Q2Data, T


SEED = 20260912
LAGS = (1, 2, 7, 14, 21, 28)
ROLLING_WINDOWS = (3, 7, 14, 28)
HGB_PARAMETERS = {
    "loss": "squared_error",
    "learning_rate": 0.06,
    "max_iter": 180,
    "max_leaf_nodes": 31,
    "min_samples_leaf": 40,
    "l2_regularization": 1.0,
    "early_stopping": False,
    "random_state": SEED,
}
ARM_MODEL_IDS = {
    "B0": "Q2V2-SW2-REC5",
    "B1": "Q2V3-HGBLOAD-HGBPV",
    "Abl-L": "Q2V3-HGBLOAD-REC5PV",
    "Abl-PV": "Q2V3-SW2LOAD-HGBPV",
}


@dataclass(frozen=True)
class ForecastBundle:
    load_b0: np.ndarray
    pv_b0: np.ndarray
    load_hgb: np.ndarray
    pv_hgb: np.ndarray
    fit_log: pd.DataFrame

    def for_arm(self, arm: str) -> tuple[np.ndarray, np.ndarray]:
        if arm == "B0":
            return self.load_b0, self.pv_b0
        if arm == "B1":
            return self.load_hgb, self.pv_hgb
        if arm == "Abl-L":
            return self.load_hgb, self.pv_b0
        if arm == "Abl-PV":
            return self.load_b0, self.pv_hgb
        raise ValueError(f"unknown forecast arm: {arm}")


def _typical_profiles() -> tuple[np.ndarray, np.ndarray]:
    frame = pd.read_excel(ATTACHMENT1)
    if frame.shape != (T, 4):
        raise ValueError(f"attachment 1 shape changed: {frame.shape}")
    load = frame.iloc[:, 2].to_numpy(float)
    pv = frame.iloc[:, 3].to_numpy(float)
    if not np.isfinite(load).all() or not np.isfinite(pv).all():
        raise ValueError("attachment 1 contains non-finite load or PV")
    return load, pv


def build_b0_forecasts(data: Q2Data) -> tuple[np.ndarray, np.ndarray]:
    """Build the frozen cold start followed by the original Q2 V2 forecasts."""
    typical_load, typical_pv = _typical_profiles()
    load = np.empty_like(data.load)
    pv = np.empty_like(data.pv)
    for day in range(len(data.dates)):
        if day < 7:
            load[day] = typical_load
        elif day < 14:
            load[day] = data.load[day - 7]
        else:
            load[day] = (data.load[day - 7] + data.load[day - 14]) / 2.0
        if day < 5:
            pv[day] = typical_pv
        else:
            pv[day] = data.pv[day - 5:day].mean(axis=0)
            # At 00:00, the previous plan day's final 00:00-00:10 interval
            # has not completed. Use five completed final-slot observations.
            if day < 6:
                pv[day, -1] = typical_pv[-1]
            else:
                pv[day, -1] = data.pv[day - 6:day - 1, -1].mean()
    return np.maximum(load, 0.0), np.maximum(pv, 0.0)


def build_b0_time_b_forecasts(data: Q2Data) -> tuple[np.ndarray, np.ndarray]:
    """Build right-endpoint B forecasts using only data visible at day d 00:00."""
    load_a, pv_a = build_b0_forecasts(data)
    load_b = shift_cross_day(load_a)
    pv_b = shift_cross_day(pv_a)
    _, typical_pv = _typical_profiles()
    for day in range(len(data.dates) - 1):
        # B[d,142] is the shifted raw 0:00+1 value. Under right-endpoint
        # semantics it was already complete at issue time, unlike A[d,143].
        if day < 5:
            pv_b[day, 142] = typical_pv[-1]
        else:
            pv_b[day, 142] = data.pv[day - 5:day, -1].mean()
        # B[d,143] targets A[d+1,0]. The precomputed A[d+1,0]
        # forecast may use day-d actual PV, which is future at issue d 00:00.
        if day < 5:
            pv_b[day, -1] = typical_pv[0]
        else:
            pv_b[day, -1] = data.pv[day - 5:day, 0].mean()
    return np.maximum(load_b, 0.0), np.maximum(pv_b, 0.0)


def build_daily_features(values: np.ndarray, dates: pd.DatetimeIndex) -> pd.DataFrame:
    n_days = len(dates)
    slots = np.tile(np.arange(T), n_days)
    out = pd.DataFrame({
        "date": np.repeat(dates.values, T),
        "slot": slots,
        "target": np.asarray(values, dtype=float).reshape(-1),
    })
    matrix = np.asarray(values, dtype=float)
    for lag in LAGS:
        lagged = np.full_like(matrix, np.nan)
        lagged[lag:] = matrix[:-lag]
        if lag == 1:
            lagged[:, -1] = np.nan
        out[f"lag_{lag}d"] = lagged.reshape(-1)

    frame = pd.DataFrame(matrix, index=dates)
    for window in ROLLING_WINDOWS:
        shifted = frame.shift(1)
        shifted.iloc[:, -1] = frame.iloc[:, -1].shift(2)
        minimum = max(2, window // 2)
        out[f"rolling_mean_{window}d"] = (
            shifted.rolling(window, min_periods=minimum).mean().to_numpy().reshape(-1)
        )
        out[f"rolling_std_{window}d"] = (
            shifted.rolling(window, min_periods=minimum).std().to_numpy().reshape(-1)
        )

    weekday_mean = np.full_like(matrix, np.nan)
    for day in range(n_days):
        candidates = np.arange(max(0, day - 35), day)
        candidates = candidates[(day - candidates) % 7 == 0][-4:]
        if len(candidates):
            weekday_mean[day] = np.nanmean(matrix[candidates], axis=0)
    out["same_weekday_mean_4"] = weekday_mean.reshape(-1)

    doy = out["date"].dt.dayofyear.to_numpy()
    dow = out["date"].dt.dayofweek.to_numpy()
    slot_angle = 2.0 * np.pi * out["slot"].to_numpy() / T
    out["slot_sin"] = np.sin(slot_angle)
    out["slot_cos"] = np.cos(slot_angle)
    out["dow_sin"] = np.sin(2.0 * np.pi * dow / 7.0)
    out["dow_cos"] = np.cos(2.0 * np.pi * dow / 7.0)
    out["doy_sin"] = np.sin(2.0 * np.pi * doy / 365.25)
    out["doy_cos"] = np.cos(2.0 * np.pi * doy / 365.25)
    out["month"] = out["date"].dt.month.astype(int)
    out["is_weekend"] = (dow >= 5).astype(int)
    out["completed_at"] = out["date"] + pd.to_timedelta(
        (out["slot"] + 2) * 10, unit="min"
    )
    return out


def feature_columns(frame: pd.DataFrame) -> list[str]:
    return [
        column for column in frame.columns
        if column not in {"date", "target", "completed_at"}
    ]


def _monthly_hgb(
    values: np.ndarray,
    dates: pd.DatetimeIndex,
    cold_start: np.ndarray,
    target_name: str,
) -> tuple[np.ndarray, list[dict]]:
    frame = build_daily_features(values, dates)
    columns = feature_columns(frame)
    predictions = np.asarray(cold_start, dtype=float).copy()
    records: list[dict] = []
    for month in pd.date_range("2025-02-01", "2025-12-01", freq="MS"):
        month_end = month + pd.offsets.MonthEnd(0)
        train = frame[(frame["completed_at"] <= month) & frame["target"].notna()]
        test = frame[(frame["date"] >= month) & (frame["date"] <= month_end)]
        if train.empty or len(test) == 0:
            raise ValueError(f"{target_name}/{month:%Y-%m}: empty train or test")
        estimator = HistGradientBoostingRegressor(**HGB_PARAMETERS)
        estimator.fit(train[columns], train["target"])
        predicted = np.maximum(estimator.predict(test[columns]), 0.0)
        day_indexes = dates.get_indexer(pd.DatetimeIndex(test["date"].unique()))
        predictions[day_indexes] = predicted.reshape(len(day_indexes), T)
        records.append({
            "target_name": target_name,
            "model": "hist_gradient_boosting",
            "forecast_month": month.strftime("%Y-%m"),
            "train_rows": int(len(train)),
            "test_rows": int(len(test)),
            "train_completed_at_max": train["completed_at"].max(),
            "feature_count": len(columns),
            "feature_columns": "|".join(columns),
        })
    if not np.isfinite(predictions).all():
        raise ValueError(f"{target_name}: non-finite predictions")
    return predictions, records


def build_forecast_bundle(
    data: Q2Data, required_arm: str | None = None
) -> ForecastBundle:
    load_b0, pv_b0 = build_b0_forecasts(data)
    if required_arm is not None and required_arm not in ARM_MODEL_IDS:
        raise ValueError(f"unknown forecast arm: {required_arm}")
    if required_arm is None or required_arm in ("B1", "Abl-L"):
        load_hgb, load_log = _monthly_hgb(
            data.load, data.dates, load_b0, "load_10min"
        )
    else:
        load_hgb, load_log = load_b0.copy(), []
    if required_arm is None or required_arm in ("B1", "Abl-PV"):
        pv_hgb, pv_log = _monthly_hgb(
            data.pv, data.dates, pv_b0, "pv_10min_history"
        )
    else:
        pv_hgb, pv_log = pv_b0.copy(), []
    return ForecastBundle(
        load_b0=load_b0,
        pv_b0=pv_b0,
        load_hgb=load_hgb,
        pv_hgb=pv_hgb,
        fit_log=pd.DataFrame(load_log + pv_log),
    )


def shift_cross_day(values: np.ndarray) -> np.ndarray:
    """Map right-endpoint observations across rows; the final value is unavailable."""
    values = np.asarray(values, dtype=float)
    if values.ndim != 2 or values.shape[1] != T:
        raise ValueError("cross-day mapping requires a day-by-144 matrix")
    shifted = np.full_like(values, np.nan)
    shifted[:, :-1] = values[:, 1:]
    shifted[:-1, -1] = values[1:, 0]
    return shifted
