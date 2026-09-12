from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class ModelSpec:
    name: str
    estimator: object | None


def make_models(seed: int, hist_params: dict) -> list[ModelSpec]:
    ridge = make_pipeline(
        SimpleImputer(strategy="median", add_indicator=True),
        StandardScaler(),
        Ridge(alpha=20.0),
    )
    hist = HistGradientBoostingRegressor(
        loss="squared_error", random_state=seed, early_stopping=False, **hist_params
    )
    return [
        ModelSpec("seasonal_naive", None),
        ModelSpec("ridge", ridge),
        ModelSpec("hist_gradient_boosting", hist),
    ]


def seasonal_naive(frame) -> np.ndarray:
    candidates = [c for c in ("lag_7d", "lag_14d", "lag_21d", "lag_28d") if c in frame]
    pred = frame[candidates].median(axis=1, skipna=True).to_numpy(dtype=float)
    fallback = frame[[c for c in frame if c.startswith("rolling_mean_")]].median(
        axis=1, skipna=True
    ).to_numpy(dtype=float)
    return np.where(np.isfinite(pred), pred, fallback)

