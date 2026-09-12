"""Strictly causal online residual adaptation for issued forecasts."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class AdaptiveConfig:
    window_days: int = 7
    weight: float = 0.75
    min_history: int = 3


def adapt_daily_forecasts(
    forecasts: pd.DataFrame,
    actual: pd.DataFrame,
    config: AdaptiveConfig = AdaptiveConfig(),
) -> pd.DataFrame:
    """Correct each slot using only errors observable before that day's 00:00 issue."""
    keys = ["target_time"]
    frame = forecasts.merge(actual[keys + ["actual"]], on=keys, how="left", validate="one_to_one")
    frame = frame.sort_values(["issue_time", "target_time"]).copy()
    frame["slot"] = (
        (frame["target_time"] - frame["issue_time"]).dt.total_seconds() / 600 - 1
    ).round().astype(int)
    frame["base_error"] = frame["actual"] - frame["prediction"]
    frame["online_correction"] = 0.0
    for slot, indices in frame.groupby("slot").groups.items():
        group = frame.loc[indices].sort_values("issue_time")
        # slot 143 is d+1 00:00-00:10 and is unfinished at issue d+1 00:00.
        shift = 2 if slot == 143 else 1
        correction = (
            group["base_error"]
            .shift(shift)
            .rolling(config.window_days, min_periods=config.min_history)
            .mean()
        )
        frame.loc[group.index, "online_correction"] = correction.fillna(0.0)
    frame["adaptive_prediction"] = np.clip(
        frame["prediction"] + config.weight * frame["online_correction"], 0, None
    )
    return frame


def adapt_intraday_block(
    day_forecast: pd.DataFrame,
    issue_time: pd.Timestamp,
    lookback_intervals: int = 12,
    weight: float = 0.75,
    block_hours: int = 6,
) -> pd.DataFrame:
    """Update the next confirmation block from completed same-day residuals."""
    completed = day_forecast[
        day_forecast["target_time"] + pd.Timedelta(minutes=10) <= issue_time
    ].tail(lookback_intervals)
    correction = (completed["actual"] - completed["prediction"]).mean()
    if not np.isfinite(correction):
        correction = 0.0
    future = day_forecast[
        (day_forecast["target_time"] > issue_time)
        & (day_forecast["target_time"] <= issue_time + pd.Timedelta(hours=block_hours))
    ].copy()
    future["adaptive_prediction"] = np.clip(future["prediction"] + weight * correction, 0, None)
    future["online_correction"] = correction
    return future
