"""Drift-aware, strictly causal residual adaptation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DriftConfig:
    long_window_days: int = 28
    short_window_days: int = 3
    drift_threshold: float = 1.5
    correction_weight: float = 0.75
    min_history_days: int = 3
    max_correction_scale: float = 2.5


def _estimate(history: pd.Series, config: DriftConfig) -> tuple[float, float, int]:
    history = history.dropna()
    if len(history) < config.min_history_days:
        return 0.0, 0.0, config.long_window_days
    recent = history.tail(config.short_window_days)
    baseline = history.tail(config.long_window_days)
    recent_mean = float(recent.mean())
    baseline_mean = float(baseline.mean())
    scale = float(baseline.std(ddof=1)) if len(baseline) > 1 else 0.0
    scale = max(scale, float(history.abs().median()) * 0.1, 1e-6)
    score = abs(recent_mean - baseline_mean) / scale
    short_weight = float(np.clip(score / max(config.drift_threshold, 1e-6), 0.0, 1.0))
    correction = (1.0 - short_weight) * baseline_mean + short_weight * recent_mean
    robust_scale = float(history.abs().quantile(0.90)) if len(history) >= 5 else np.inf
    correction = float(np.clip(correction, -config.max_correction_scale * robust_scale,
                               config.max_correction_scale * robust_scale))
    window = config.short_window_days if score >= config.drift_threshold else config.long_window_days
    return correction, float(score), window


def adapt_daily_forecasts(
    forecasts: pd.DataFrame,
    actual: pd.DataFrame,
    config: DriftConfig = DriftConfig(),
) -> pd.DataFrame:
    """Update issued forecasts using only residuals complete before each issue."""
    forecasts = forecasts.copy()
    actual = actual[["target_time", "actual"]].copy()
    for column in ("issue_time", "target_time", "completed_at"):
        if column in forecasts:
            forecasts[column] = pd.to_datetime(forecasts[column], errors="raise")
    actual["target_time"] = pd.to_datetime(actual["target_time"], errors="raise")
    frame = forecasts.merge(
        actual[["target_time", "actual"]], on="target_time", how="left", validate="one_to_one"
    ).sort_values(["issue_time", "target_time"]).copy()
    frame["slot"] = ((frame["target_time"] - frame["issue_time"]).dt.total_seconds() / 600 - 1).round().astype(int)
    frame["base_error"] = frame["actual"] - frame["prediction"]
    if "completed_at" not in frame:
        frame["completed_at"] = frame["target_time"] + pd.Timedelta(minutes=10)
    frame["online_correction"] = 0.0
    frame["drift_score"] = 0.0
    frame["adaptive_window_days"] = config.long_window_days
    for slot, indices in frame.groupby("slot").groups.items():
        group = frame.loc[indices].sort_values("issue_time")
        values = []
        scores = []
        windows = []
        for pos in range(len(group)):
            cutoff = group.iloc[pos]["issue_time"]
            history = group[(group["completed_at"] <= cutoff) & (group["issue_time"] < cutoff)]
            correction, score, window = _estimate(
                history["base_error"].tail(config.long_window_days), config
            )
            values.append(correction)
            scores.append(score)
            windows.append(window)
        frame.loc[group.index, "online_correction"] = values
        frame.loc[group.index, "drift_score"] = scores
        frame.loc[group.index, "adaptive_window_days"] = windows
    frame["adaptive_prediction"] = np.clip(
        frame["prediction"] + config.correction_weight * frame["online_correction"], 0, None
    )
    return frame
