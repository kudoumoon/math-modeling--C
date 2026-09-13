"""Q2 深度搜索的严格因果预测、风险和场景工具。"""
from __future__ import annotations

import numpy as np


def weighted_quantile(values, quantile: float, weights=None) -> float:
    values = np.asarray(values, dtype=float).ravel()
    if weights is None:
        return float(np.quantile(values, quantile))
    weights = np.asarray(weights, dtype=float).ravel()
    mask = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    values, weights = values[mask], weights[mask]
    if not len(values):
        return 0.0
    order = np.argsort(values, kind="mergesort")
    values, weights = values[order], weights[order]
    cumulative = np.cumsum(weights) / weights.sum()
    return float(values[min(np.searchsorted(cumulative, quantile, side="left"), len(values)-1)])


def s2_load_forecast(load: np.ndarray) -> np.ndarray:
    """方案6复刻：最多四个过去同星期日均值，加最近同星期日均值偏差的一半。"""
    load = np.asarray(load, dtype=float)
    pred = np.full_like(load, np.nan)
    for day in range(7, len(load)):
        idx = np.arange(day - 7, max(-1, day - 29), -7, dtype=int)
        idx = idx[idx >= 0][:4]
        base = load[idx].mean(axis=0)
        ref_mean = float(load[idx].mean())
        correction = (float(load[idx[0]].mean()) - ref_mean) / 2.0
        correction = float(np.clip(correction, -0.2 * ref_mean, 0.2 * ref_mean))
        pred[day] = np.maximum(base + correction, 0.0)
    return pred


def s2_pv_forecast(pv: np.ndarray, recent_days: int = 7,
                   yesterday_weight: float = 0.5) -> np.ndarray:
    """方案6复刻：昨日曲线与过去至多 recent_days 日均值融合。"""
    pv = np.asarray(pv, dtype=float)
    pred = np.full_like(pv, np.nan)
    for day in range(1, len(pv)):
        recent = pv[max(0, day - recent_days):day].mean(axis=0)
        pred[day] = yesterday_weight * pv[day - 1] + (1.0 - yesterday_weight) * recent
    return np.maximum(pred, 0.0)


def recency_weights(indices: np.ndarray, day: int, gamma: float) -> np.ndarray:
    indices = np.asarray(indices, dtype=int)
    raw = np.exp(-float(gamma) * (day - indices - 1))
    return raw / raw.sum()


def rolling_weighted_margin(residuals: np.ndarray, day: int, alpha: float,
                            window: int, gamma: float, structure: str = "time",
                            block_hours: int = 2) -> np.ndarray:
    start = max(0, day - window)
    hist = residuals[start:day]
    valid = ~np.isnan(hist).any(axis=1)
    hist = hist[valid]
    indices = np.arange(start, day)[valid]
    if not len(hist):
        return np.zeros(residuals.shape[1])
    weights = recency_weights(indices, day, gamma)
    T = residuals.shape[1]
    if structure == "time":
        out = np.array([weighted_quantile(hist[:, k], alpha, weights) for k in range(T)])
    elif structure == "global":
        out = np.full(T, weighted_quantile(hist.ravel(), alpha, np.repeat(weights, T)))
    elif structure == "block":
        out = np.zeros(T)
        block = block_hours * 6
        for lo in range(0, T, block):
            hi = min(T, lo + block)
            out[lo:hi] = weighted_quantile(hist[:, lo:hi].ravel(), alpha,
                                           np.repeat(weights, hi-lo))
    else:
        raise ValueError(structure)
    return np.maximum(out, 0.0)


def select_day_type_candidates(dates, day: int, window: int,
                               pv_total: np.ndarray, load_total: np.ndarray) -> np.ndarray:
    """只按当日0点已知类别筛选过去样本，样本不足时逐级放宽。"""
    dates = np.asarray(dates).astype("datetime64[D]")
    start = max(0, day - window)
    candidates = np.arange(start, day)
    weekday = int((dates[day].astype(int) + 3) % 7) < 5
    cand_weekday = ((dates[candidates].astype(int) + 3) % 7) < 5
    season = int(str(dates[day])[5:7]) // 4
    cand_season = np.array([int(str(x)[5:7]) // 4 for x in dates[candidates]])
    pv_high = pv_total[day] >= np.nanmedian(pv_total[:day])
    load_high = load_total[day] >= np.nanmedian(load_total[:day])
    mask = ((cand_weekday == weekday) & (cand_season == season)
            & ((pv_total[candidates] >= np.nanmedian(pv_total[:day])) == pv_high)
            & ((load_total[candidates] >= np.nanmedian(load_total[:day])) == load_high))
    chosen = candidates[mask]
    if len(chosen) < 10:
        chosen = candidates[cand_weekday == weekday]
    if len(chosen) < 10:
        chosen = candidates
    return chosen
