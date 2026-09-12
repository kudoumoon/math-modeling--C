"""Isolated, reproducible forecast experiments and evidence for independent review."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

import numpy as np
import pandas as pd

from .backtest import run_backtest
from .forecast_value import run_forecast_value
from .rolling_backtest import _bootstrap_mean


BASELINES = {"load_10min": "seasonal_naive", "price_10min": "seasonal_naive",
             "pv_hourly": "raw_official"}
KEYS = ["target_name", "issue_time", "target_time"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def metric_row(frame: pd.DataFrame, coverage: float = 0.8) -> dict:
    valid = frame["target"].notna() & np.isfinite(frame["prediction"])
    part = frame[valid]
    error = part["prediction"] - part["target"]
    result = {"n_requests": len(frame), "n_scored": len(part),
              "n_missing_actual": int(frame["target"].isna().sum()),
              "mae": error.abs().mean(), "rmse": np.sqrt((error ** 2).mean()),
              "bias": error.mean()}
    if {"lower", "upper"} <= set(part):
        interval = part[part["lower"].notna() & part["upper"].notna()]
        width = interval["upper"] - interval["lower"]
        score = width + (2 / (1 - coverage)) * (
            (interval["lower"] - interval["target"]).clip(lower=0)
            + (interval["target"] - interval["upper"]).clip(lower=0))
        result.update(n_intervals=len(interval),
                      interval_valid_fraction=len(interval) / max(1, len(part)),
                      interval_coverage=interval["target"].between(interval["lower"], interval["upper"]).mean(),
                      interval_width=width.mean(), interval_score=score.mean())
    return result


def evaluate_forecasts(run_dir: Path, cfg: dict) -> dict:
    candidates = pd.read_csv(run_dir / "predictions/candidate_predictions.csv",
                             parse_dates=["issue_time", "target_time"])
    selected = pd.read_csv(run_dir / "predictions/causal_forecasts.csv",
                           parse_dates=["issue_time", "target_time"])
    if candidates.duplicated(KEYS + ["model"]).any() or selected.duplicated(KEYS).any():
        raise ValueError("forecast keys must be unique")
    if not np.isfinite(selected["prediction"]).all():
        raise ValueError("selected predictions must be finite")
    labels = candidates[KEYS + ["model", "target"]]
    detail = selected.merge(labels, on=KEYS + ["model"], validate="one_to_one")
    if len(detail) != len(selected):
        raise ValueError("selected forecasts lost evaluation keys")
    detail["month"] = detail["issue_time"].dt.strftime("%Y-%m")
    detail["hour"] = detail["target_time"].dt.hour
    detail["lead_band"] = ((detail["lead_hour"] - 1) // 6 + 1)
    rows = []
    for dimension in ("all", "month", "hour", "issue_hour", "lead_band"):
        group_columns = ["target_name", "model", "split"]
        if dimension != "all":
            group_columns.append(dimension)
        for keys, part in detail.groupby(group_columns, dropna=False):
            if dimension in ("issue_hour", "lead_band") and keys[0] != "pv_hourly":
                continue
            rows.append(dict(target_name=keys[0], model=keys[1], split=keys[2],
                             dimension=dimension, stratum=str(keys[3]) if len(keys) > 3 else "all",
                             **metric_row(part, cfg["interval_coverage"])))
    pd.DataFrame(rows).to_csv(run_dir / "reports/forecast_strata.csv", index=False)
    comparisons = []
    daily_rows = []
    for target, baseline_name in BASELINES.items():
        baseline = candidates[(candidates.target_name == target) & (candidates.model == baseline_name)]
        paired = detail[detail.target_name == target].merge(
            baseline[KEYS + ["prediction"]].rename(columns={"prediction": "baseline_prediction"}),
            on=KEYS, validate="one_to_one")
        if len(paired) != len(detail[detail.target_name == target]):
            raise ValueError(f"missing common baseline samples for {target}")
        paired = paired[paired.target.notna()].copy()
        paired["mae_gain"] = (paired.baseline_prediction - paired.target).abs() - (paired.prediction - paired.target).abs()
        paired["date"] = paired.issue_time.dt.normalize()
        for split, part in paired.groupby("split"):
            days = part.groupby("date").mae_gain.mean()
            for date, gain in days.items():
                daily_rows.append(dict(target_name=target, split=split, date=date, mae_gain=gain))
            for block in (3, 7, 14):
                comparisons.append(dict(target_name=target, baseline=baseline_name, split=split,
                                        block_days=block, n_days=len(days),
                                        **_bootstrap_mean(days.to_numpy(), block=block, seed=cfg["seed"])))
    pd.DataFrame(comparisons).to_csv(run_dir / "reports/forecast_gain_bootstrap.csv", index=False)
    pd.DataFrame(daily_rows).to_csv(run_dir / "reports/forecast_gain_daily.csv", index=False)
    detail.to_csv(run_dir / "reports/forecast_evaluation_detail.csv", index=False)
    return {"prediction_rows": len(selected), "scored_rows": int(detail.target.notna().sum()),
            "unscored_rows": int(detail.target.isna().sum())}


def _reuse_forecasts(root: Path, parent: Path, destination: Path, cfg_hash: str,
                    inputs: dict) -> dict:
    previous = json.loads((parent / "manifest.json").read_text(encoding="utf-8"))
    if previous["config_sha256"] != cfg_hash or previous["input_hashes"] != inputs:
        raise ValueError("cached forecasts use different configuration or frozen inputs")
    dependencies = [f"src/forecasting/{name}.py" for name in ("data", "features", "models", "backtest")]
    for dependency in dependencies:
        digest = previous["source_hashes"].get(dependency)
        if digest != sha256(root / dependency) or digest != sha256(parent / "snapshot" / dependency):
            raise ValueError(f"cached training dependency changed: {dependency}")
    files = ["predictions/causal_forecasts.csv", "predictions/candidate_predictions.csv",
             "reports/candidate_metrics.csv", "reports/selected_model_metrics.csv",
             "reports/forecast_backtest.md", "artifacts/selected_models.json"]
    files += [str(p.relative_to(parent)) for p in sorted((parent / "artifacts/models").rglob("*")) if p.is_file()]
    hashes = {}
    for relative in files:
        source = parent / relative
        hashes[relative] = sha256(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if sha256(target) != hashes[relative]:
            raise ValueError(f"cache copy mismatch: {relative}")
    return {"parent_run": str(parent), "parent_status": previous["status"],
            "training_dependencies": dependencies, "copied_hashes": hashes,
            "reason": "Only training-independent evaluation changed; prediction and model bytes are reused."}


def run_experiment(root: str | Path, config: str, run_id: str,
                   reuse_forecast_run: str | None = None) -> Path:
    root = Path(root).resolve()
    if not run_id or Path(run_id).name != run_id or run_id in (".", ".."):
        raise ValueError("run_id must be a single directory name")
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    config_path = root / config
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    frozen = json.loads((root / "data_manifest.json").read_text(encoding="utf-8"))
    inputs = {}
    for entry in frozen["files"]:
        actual_hash = sha256(root / entry["path"])
        if actual_hash != entry["sha256"]:
            raise ValueError(f"frozen input hash mismatch: {entry['path']}")
        inputs[entry["path"]] = actual_hash
    source_files = sorted((root / "src").rglob("*.py")) + sorted((root / "tests").rglob("*.py"))
    source_files += [root / "pyproject.toml", root / "docs/预测器双Agent验收规约.md",
                     root / "docs/预测输出时间与接入契约.md"]
    source_hashes = {}
    for source in source_files:
        relative = source.relative_to(root)
        target = run_dir / "snapshot" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        source_hashes[str(relative)] = sha256(source)
    shutil.copy2(config_path, run_dir / "config.json")
    packages = {name: importlib.metadata.version(name) for name in (
        "numpy", "pandas", "scipy", "scikit-learn", "joblib", "openpyxl", "pytest")}
    manifest = {"run_id": run_id, "status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
                "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
                "input_hashes": inputs, "source_hashes": source_hashes,
                "config_sha256": sha256(config_path), "packages": packages,
                "python": sys.version, "platform": platform.platform(), "seed": cfg["seed"],
                "thread_environment": {k: os.environ.get(k) for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
                "command": [sys.executable, "-m", "forecasting.experiment", "--root", str(root),
                            "--config", config, "--run-id", run_id],
                "audit_interpretation": "Retrospective only; never used for iterative model selection."}
    _write_json(run_dir / "manifest.json", manifest)
    start = time.monotonic()
    try:
        if reuse_forecast_run is None:
            print(f"[{run_id}] training frozen monthly candidates", flush=True)
            result = run_backtest(root, config, output_root=run_dir)
        else:
            print(f"[{run_id}] verifying cached forecast dependencies", flush=True)
            manifest["command"] += ["--reuse-forecast-run", reuse_forecast_run]
            manifest["forecast_reuse"] = _reuse_forecasts(
                root, root / reuse_forecast_run, run_dir, sha256(config_path), inputs)
            result = {"selected_models": json.loads((run_dir / "artifacts/selected_models.json").read_text())}
        print(f"[{run_id}] computing paired and stratified forecast evidence", flush=True)
        manifest["evaluation"] = evaluate_forecasts(run_dir, cfg)
        manifest["selected_models"] = result["selected_models"]
        print(f"[{run_id}] replaying fixed causal dispatch proxy", flush=True)
        manifest["forecast_value"] = run_forecast_value(root, run_dir, cfg)
        changed = [str(p.relative_to(root)) for p in source_files if sha256(p) != source_hashes[str(p.relative_to(root))]]
        if changed:
            raise RuntimeError(f"source changed during experiment: {changed}")
        manifest["status"] = "complete"
        manifest["outputs"] = {str(p.relative_to(run_dir)): sha256(p)
                               for folder in ("reports", "predictions", "artifacts")
                               for p in sorted((run_dir / folder).rglob("*")) if p.is_file()}
    except BaseException as exc:
        manifest["status"] = "failed"
        manifest["error"] = repr(exc)
        raise
    finally:
        manifest["elapsed_seconds"] = time.monotonic() - start
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(run_dir / "manifest.json", manifest)
    print(f"[{run_id}] complete: {run_dir}", flush=True)
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default="configs/forecast.json")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--reuse-forecast-run", default=None)
    args = parser.parse_args()
    run_experiment(args.root, args.config, args.run_id, args.reuse_forecast_run)


if __name__ == "__main__":
    main()
