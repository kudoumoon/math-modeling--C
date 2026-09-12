from __future__ import annotations

import numpy as np
import pandas as pd

from .data import SLOTS_PER_DAY


LAGS = (1, 2, 7, 14, 21, 28)
ROLLING_WINDOWS = (3, 7, 14, 28)


def build_daily_features(values: pd.DataFrame) -> pd.DataFrame:
    """Features available at date d 00:00; every value feature is explicitly shifted."""
    n_days = len(values)
    dates = np.repeat(values.index.values, SLOTS_PER_DAY)
    slots = np.tile(np.arange(SLOTS_PER_DAY), n_days)
    out = pd.DataFrame({"date": pd.to_datetime(dates), "slot": slots})
    out["target"] = values.to_numpy().reshape(-1)

    matrix = values.to_numpy(dtype=float)
    for lag in LAGS:
        lagged = np.full_like(matrix, np.nan)
        lagged[lag:] = matrix[:-lag]
        # Row d-1 slot 143 is the interval d 00:00-00:10 and is not complete at d 00:00.
        if lag == 1:
            lagged[:, -1] = np.nan
        out[f"lag_{lag}d"] = lagged.reshape(-1)

    frame = pd.DataFrame(matrix, index=values.index)
    for window in ROLLING_WINDOWS:
        shifted = frame.shift(1)
        shifted.iloc[:, -1] = frame.iloc[:, -1].shift(2)
        mean = shifted.rolling(window, min_periods=max(2, window // 2)).mean().to_numpy(copy=True)
        std = shifted.rolling(window, min_periods=max(2, window // 2)).std().to_numpy(copy=True)
        out[f"rolling_mean_{window}d"] = mean.reshape(-1)
        out[f"rolling_std_{window}d"] = std.reshape(-1)

    weekday_mean = np.full_like(matrix, np.nan)
    for i in range(n_days):
        candidates = np.arange(max(0, i - 35), i)
        candidates = candidates[(i - candidates) % 7 == 0][-4:]
        if len(candidates):
            weekday_mean[i] = np.nanmean(matrix[candidates], axis=0)
    out["same_weekday_mean_4"] = weekday_mean.reshape(-1)

    doy = out["date"].dt.dayofyear.to_numpy()
    dow = out["date"].dt.dayofweek.to_numpy()
    angle_slot = 2 * np.pi * out["slot"].to_numpy() / SLOTS_PER_DAY
    out["slot_sin"] = np.sin(angle_slot)
    out["slot_cos"] = np.cos(angle_slot)
    out["dow_sin"] = np.sin(2 * np.pi * dow / 7)
    out["dow_cos"] = np.cos(2 * np.pi * dow / 7)
    out["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    out["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    out["month"] = out["date"].dt.month.astype(int)
    out["is_weekend"] = (dow >= 5).astype(int)
    return out


def build_pv_calibration_features(forecasts: pd.DataFrame) -> pd.DataFrame:
    out = forecasts.copy()
    target_doy = out["target_time"].dt.dayofyear.to_numpy()
    target_hour = out["target_time"].dt.hour.to_numpy()
    out["raw_pv_sqrt"] = np.sqrt(out["raw_pv"].clip(lower=0))
    out["raw_pv_log1p"] = np.log1p(out["raw_pv"].clip(lower=0))
    out["target_hour_sin"] = np.sin(2 * np.pi * target_hour / 24)
    out["target_hour_cos"] = np.cos(2 * np.pi * target_hour / 24)
    out["target_doy_sin"] = np.sin(2 * np.pi * target_doy / 365.25)
    out["target_doy_cos"] = np.cos(2 * np.pi * target_doy / 365.25)
    out["issue_hour_sin"] = np.sin(2 * np.pi * out["issue_hour"] / 24)
    out["issue_hour_cos"] = np.cos(2 * np.pi * out["issue_hour"] / 24)
    out["daylight"] = (out["raw_pv"] > 0).astype(int)
    return out


def feature_columns(frame: pd.DataFrame, pv: bool = False) -> list[str]:
    blocked = {
        "target", "date", "actual_pv", "actual_intervals", "issue_time", "target_time",
        "window_start", "window_end", "raw_pv", "completed_at",
    }
    if pv:
        allowed = {
            "lead_hour", "issue_hour", "raw_pv_sqrt", "raw_pv_log1p", "target_hour_sin",
            "target_hour_cos", "target_doy_sin", "target_doy_cos", "issue_hour_sin",
            "issue_hour_cos", "daylight",
        }
        return [c for c in frame.columns if c in allowed]
    return [c for c in frame.columns if c not in blocked]
