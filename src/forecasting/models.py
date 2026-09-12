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


def make_models(seed: int, hist_params: dict, models: list[str] | None = None) -> list[ModelSpec]:
    names = ["seasonal_naive", "ridge", "hist_gradient_boosting"] if models is None else models
    allowed = {"seasonal_naive", "ridge", "hist_gradient_boosting"}
    if (not isinstance(names, list) or not names
            or any(not isinstance(name, str) or name not in allowed for name in names)
            or len(set(names)) != len(names)):
        raise ValueError("models must be a nonempty list of unique supported model names")
    ridge = make_pipeline(
        SimpleImputer(strategy="median", add_indicator=True),
        StandardScaler(),
        Ridge(alpha=20.0),
    )
    estimators = {"seasonal_naive": None, "ridge": ridge}
    if "hist_gradient_boosting" in names:
        estimators["hist_gradient_boosting"] = HistGradientBoostingRegressor(
            loss="squared_error", random_state=seed, early_stopping=False, **hist_params
        )
    return [ModelSpec(name, estimators[name]) for name in names]


def seasonal_naive(frame) -> np.ndarray:
    candidates = [c for c in ("lag_7d", "lag_14d", "lag_21d", "lag_28d") if c in frame]
    pred = frame[candidates].median(axis=1, skipna=True).to_numpy(dtype=float)
    fallback = frame[[c for c in frame if c.startswith("rolling_mean_")]].median(
        axis=1, skipna=True
    ).to_numpy(dtype=float)
    result = np.where(np.isfinite(pred), pred, fallback)
    if not np.isfinite(result).all():
        raise ValueError("seasonal_naive requires completed historical observations; cold start is unsupported")
    return result
