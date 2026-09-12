from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from sklearn.base import clone
from sklearn.metrics import mean_absolute_error, mean_squared_error

from .data import ProblemData, SLOTS_PER_DAY, daily_to_long, load_problem_data
from .features import build_daily_features, build_pv_calibration_features, feature_columns
from .models import make_models, seasonal_naive


def _month_starts(first: pd.Timestamp, last: pd.Timestamp) -> list[pd.Timestamp]:
    return list(pd.date_range(first.replace(day=1), last.replace(day=1), freq="MS"))


def _split_name(date: pd.Series, cfg: dict) -> np.ndarray:
    return np.where(date <= pd.Timestamp(cfg["development_end"]), "development", "audit")


def _save_fitted(estimator, columns: list[str], target: str, model: str,
                 month: pd.Timestamp, train_end: pd.Timestamp, artifact_dir: Path | None,
                 residual: bool = False) -> None:
    if artifact_dir is None:
        return
    destination = Path(artifact_dir) / "models" / target / month.strftime("%Y-%m")
    destination.mkdir(parents=True, exist_ok=True)
    joblib.dump({"estimator": estimator, "feature_columns": columns, "target_name": target,
                 "model": model, "train_end": train_end, "history_cutoff": month,
                 "predicts_residual": residual, "clip_lower": 0.0}, destination / f"{model}.joblib")
    (destination / f"{model}.features.json").write_text(json.dumps(columns, indent=2), encoding="utf-8")


def _daily_candidate_predictions(values: pd.DataFrame, target_name: str, cfg: dict,
                                 artifact_dir: Path | None = None) -> pd.DataFrame:
    frame = build_daily_features(values)
    columns = feature_columns(frame)
    frame["completed_at"] = frame["date"] + pd.to_timedelta((frame["slot"] + 2) * 10, unit="min")
    first = pd.Timestamp(cfg["first_forecast_date"])
    last = pd.Timestamp(cfg["last_forecast_date"])
    outputs: list[pd.DataFrame] = []
    specs = make_models(cfg["seed"], cfg["hist_gradient_boosting"], cfg.get("models"))
    for month in _month_starts(first, last):
        month_end = min(month + pd.offsets.MonthEnd(0), last)
        train = frame[(frame["completed_at"] <= month) & frame["target"].notna()]
        test = frame[(frame["date"] >= max(month, first)) & (frame["date"] <= month_end)]
        if test.empty:
            continue
        for spec in specs:
            if spec.name == "seasonal_naive":
                pred = seasonal_naive(test)
            else:
                if train.empty:
                    raise ValueError(f"{target_name}/{spec.name}: no completed training labels at {month}")
                estimator = clone(spec.estimator)
                estimator.fit(train[columns], train["target"])
                pred = estimator.predict(test[columns])
                _save_fitted(estimator, columns, target_name, spec.name, month,
                             train["completed_at"].max(), artifact_dir)
            part = test[["date", "slot", "target", "completed_at"]].copy()
            part["prediction"] = np.clip(pred, 0, None)
            part["model"] = spec.name
            part["target_name"] = target_name
            part["train_end"] = pd.NaT if spec.name == "seasonal_naive" else train["completed_at"].max()
            part["history_cutoff"] = part["date"] if spec.name == "seasonal_naive" else month
            outputs.append(part)
    result = pd.concat(outputs, ignore_index=True)
    result["issue_time"] = result["date"]
    result["target_time"] = result["date"] + pd.to_timedelta((result["slot"] + 1) * 10, unit="min")
    result["interval_start"] = result["target_time"]
    result["interval_end"] = result["completed_at"]
    result["unit"] = "yuan/kWh" if target_name == "price_10min" else "kW"
    result["split"] = _split_name(result["date"], cfg)
    return result


def _pv_candidate_predictions(data: ProblemData, cfg: dict,
                              artifact_dir: Path | None = None) -> pd.DataFrame:
    frame = build_pv_calibration_features(data.pv_forecasts)
    columns = feature_columns(frame, pv=True)
    first = pd.Timestamp(cfg["first_forecast_date"])
    last = pd.Timestamp(cfg["last_forecast_date"]) + pd.Timedelta(hours=23, minutes=59)
    outputs: list[pd.DataFrame] = []
    model_specs = [s for s in make_models(cfg["seed"], cfg["hist_gradient_boosting"], cfg.get("models")) if s.name != "seasonal_naive"]
    for month in _month_starts(first, pd.Timestamp(cfg["last_forecast_date"])):
        month_end = min(month + pd.offsets.MonthEnd(0) + pd.Timedelta(hours=23, minutes=59), last)
        # A forecast becomes a training label only after all six target intervals are complete.
        train = frame[(frame["window_end"] <= month) & frame["actual_pv"].notna()]
        test = frame[(frame["issue_time"] >= max(month, first)) & (frame["issue_time"] <= month_end)]
        if test.empty:
            continue
        raw = test["raw_pv"].to_numpy(float)
        base = test[["issue_time", "target_time", "lead_hour", "issue_hour", "actual_pv", "raw_pv"]].copy()
        base["completed_at"] = test["window_end"]
        base["prediction"] = raw
        base["model"] = "raw_official"
        base["train_end"] = pd.NaT
        base["history_cutoff"] = base["issue_time"]
        outputs.append(base)
        for spec in model_specs:
            if train.empty:
                raise ValueError(f"pv_hourly/{spec.name}: no completed training labels at {month}")
            estimator = clone(spec.estimator)
            residual = train["actual_pv"] - train["raw_pv"]
            estimator.fit(train[columns], residual)
            pred = raw + estimator.predict(test[columns])
            part = base.copy()
            part["prediction"] = np.clip(pred, 0, None)
            part["model"] = f"{spec.name}_residual"
            part["train_end"] = train["window_end"].max()
            part["history_cutoff"] = month
            _save_fitted(estimator, columns, "pv_hourly", f"{spec.name}_residual", month,
                         train["window_end"].max(), artifact_dir, residual=True)
            outputs.append(part)
    result = pd.concat(outputs, ignore_index=True)
    result["date"] = result["issue_time"].dt.normalize()
    result["target_name"] = "pv_hourly"
    result["target"] = result["actual_pv"]
    result["interval_end"] = result["completed_at"]
    result["interval_start"] = result["interval_end"] - pd.Timedelta(hours=1)
    result["unit"] = "kW"
    result["split"] = _split_name(result["date"], cfg)
    return result


def _select_on_development(predictions: pd.DataFrame) -> dict[str, str]:
    selected: dict[str, str] = {}
    for target, part in predictions[(predictions["split"] == "development") & predictions["target"].notna()].groupby("target_name"):
        scores = part.groupby("model").apply(
            lambda x: mean_absolute_error(x["target"], x["prediction"]), include_groups=False
        )
        selected[target] = str(scores.idxmin())
    return selected


def _causal_intervals(selected: pd.DataFrame, coverage: float, window_days: int) -> pd.DataFrame:
    alpha = 1 - coverage
    out = selected.sort_values(["target_name", "model", "issue_time", "target_time"]).copy()
    if "completed_at" not in out:
        out["completed_at"] = out["target_time"] + pd.Timedelta(minutes=10)
    out["lower"] = np.nan
    out["upper"] = np.nan
    for (_, _), idx in out.groupby(["target_name", "model"]).groups.items():
        group = out.loc[idx].sort_values(["issue_time", "target_time"])
        for issue_time, day_idx in group.groupby("issue_time").groups.items():
            cutoff = pd.Timestamp(issue_time)
            history = group[
                (group["completed_at"] <= cutoff)
                & (group["completed_at"] >= cutoff - pd.Timedelta(days=window_days))
                & (group["issue_time"] < cutoff)
            ]
            abs_error = (history["target"] - history["prediction"]).abs().dropna()
            radius = abs_error.quantile(1 - alpha) if len(abs_error) >= 30 else np.nan
            pred = group.loc[day_idx, "prediction"]
            out.loc[day_idx, "lower"] = np.clip(pred - radius, 0, None)
            out.loc[day_idx, "upper"] = pred + radius
    return out


def _metrics(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for keys, part in predictions.groupby(["target_name", "model", "split"]):
        n_predictions = len(part)
        part = part[part["target"].notna()]
        error = part["prediction"] - part["target"]
        valid_interval = (part["lower"].notna() & part["upper"].notna()) if "lower" in part else pd.Series(False, index=part.index)
        coverage = (
            ((part.loc[valid_interval, "target"] >= part.loc[valid_interval, "lower"])
             & (part.loc[valid_interval, "target"] <= part.loc[valid_interval, "upper"])).mean()
            if valid_interval.any() else np.nan
        )
        rows.append({
            "target": keys[0], "model": keys[1], "split": keys[2], "n": len(part),
            "n_predictions": n_predictions, "n_missing_actual": n_predictions - len(part),
            "n_intervals": int(valid_interval.sum()),
            "mae": float(np.mean(np.abs(error))), "rmse": float(np.sqrt(np.mean(error ** 2))),
            "bias": float(np.mean(error)), "interval_coverage": float(coverage) if np.isfinite(coverage) else np.nan,
        })
    return pd.DataFrame(rows).sort_values(["target", "split", "mae"])


def _write_report(metrics: pd.DataFrame, selected: dict[str, str], output: Path, cfg: dict) -> None:
    lines = [
        "# Q3/Q4 因果预测模型回测报告", "",
        "本报告由 `PYTHONPATH=src .venv/bin/python -m forecasting.cli` 生成。所有模型按月扩展窗口重训；模型选择仅使用2025-02至2025-06，2025-07至2025-12为回顾性审计区间。", "",
        "## 开发期选定模型", "",
    ]
    for target, model in selected.items():
        lines.append(f"- `{target}`：`{model}`")
    lines += ["", "## 指标", "", metrics.to_markdown(index=False, floatfmt=".4f"), "",
              "## 信息边界", "",
              "- 负荷与价格预测只使用目标日之前已完成日期的滞后量和滚动统计。",
              "- 前一日最后一个 `0:00–0:10+1` 区间在当日0:00尚未完成，特征中显式置空。",
              "- 光伏模型只校准附件3在各发布时刻已经给出的预报；训练标签必须在发布时刻前已完整形成。",
              "- 预测区间只使用当前发布时刻之前已完成目标的历史残差。",
              "- 审计区间此前已在仓库文档中出现过汇总结果，因此只能称回顾性审计，不能称全新未见测试。", ""]
    output.write_text("\n".join(lines), encoding="utf-8")


def run_backtest(root: str | Path = ".", config_path: str | Path = "configs/forecast.json",
                 output_root: str | Path | None = None) -> dict:
    root = Path(root)
    output_root = root if output_root is None else Path(output_root)
    cfg = json.loads((root / config_path).read_text(encoding="utf-8"))
    data = load_problem_data(root)
    artifact_dir = output_root / "artifacts"
    load_pred = _daily_candidate_predictions(data.load, "load_10min", cfg, artifact_dir=artifact_dir)
    price_pred = _daily_candidate_predictions(data.price, "price_10min", cfg, artifact_dir=artifact_dir)
    pv_pred = _pv_candidate_predictions(data, cfg, artifact_dir=artifact_dir)
    candidates = pd.concat([load_pred, price_pred, pv_pred], ignore_index=True, sort=False)
    selected_models = _select_on_development(candidates)
    selected = pd.concat([
        part[part["model"] == selected_models[target]]
        for target, part in candidates.groupby("target_name")
    ], ignore_index=True, sort=False)
    selected = _causal_intervals(selected, cfg["interval_coverage"], cfg["residual_window_days"])
    candidate_metrics = _metrics(candidates.assign(lower=np.nan, upper=np.nan))
    selected_metrics = _metrics(selected)

    pred_dir = output_root / "predictions"; report_dir = output_root / "reports"; artifact_dir = output_root / "artifacts"
    pred_dir.mkdir(parents=True, exist_ok=True); report_dir.mkdir(parents=True, exist_ok=True); artifact_dir.mkdir(parents=True, exist_ok=True)
    columns = [c for c in ["target_name", "model", "issue_time", "target_time", "lead_hour", "issue_hour",
                              "prediction", "lower", "upper", "split", "train_end", "completed_at",
                              "history_cutoff", "interval_start", "interval_end", "unit"] if c in selected]
    selected[columns].to_csv(pred_dir / "causal_forecasts.csv", index=False, date_format="%Y-%m-%d %H:%M:%S")
    candidates.to_csv(pred_dir / "candidate_predictions.csv", index=False, date_format="%Y-%m-%d %H:%M:%S")
    candidate_metrics.to_csv(report_dir / "candidate_metrics.csv", index=False)
    selected_metrics.to_csv(report_dir / "selected_model_metrics.csv", index=False)
    (artifact_dir / "selected_models.json").write_text(
        json.dumps(selected_models, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_report(selected_metrics, selected_models, report_dir / "forecast_backtest.md", cfg)
    return {"selected_models": selected_models, "metrics": selected_metrics.to_dict("records")}
