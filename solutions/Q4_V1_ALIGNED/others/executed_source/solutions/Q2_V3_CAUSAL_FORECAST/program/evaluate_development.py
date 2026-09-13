"""Apply the frozen development-only adoption rule to the four Q2 V3 arms."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from q2_forecasts import ARM_MODEL_IDS
from q2_model import load_data


ARM_ORDER = ("B0", "Abl-L", "Abl-PV", "B1")
ASSET_VALUE = 0.4684
SEED = 20260912
N_BOOTSTRAP = 2000


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def block_bootstrap(values: np.ndarray, block: int) -> dict[str, float]:
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or len(values) == 0:
        raise ValueError("bootstrap values must be a nonempty vector")
    rng = np.random.default_rng(SEED + block)
    starts = np.arange(len(values))
    draws = np.empty(N_BOOTSTRAP)
    blocks_needed = math.ceil(len(values) / block)
    for draw in range(N_BOOTSTRAP):
        chosen = rng.choice(starts, size=blocks_needed, replace=True)
        sample = np.concatenate([
            values[(start + np.arange(block)) % len(values)]
            for start in chosen
        ])[:len(values)]
        draws[draw] = sample.mean()
    return {
        "mean_daily_difference_yuan": float(values.mean()),
        "lower_95_yuan": float(np.quantile(draws, 0.025)),
        "upper_95_yuan": float(np.quantile(draws, 0.975)),
    }


def empirical_cvar95(values: pd.Series) -> float:
    count = max(1, math.ceil(0.05 * len(values)))
    return float(np.sort(values.to_numpy(float))[-count:].mean())


def load_run(path: Path, arm: str) -> tuple[dict, pd.DataFrame, dict]:
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads((path / "config.json").read_text(encoding="utf-8"))
    if manifest["status"] != "complete":
        raise ValueError(f"{arm}: run is not complete")
    if config["forecast_arm"] != arm or config["forecast_model_id"] != ARM_MODEL_IDS[arm]:
        raise ValueError(f"{arm}: forecast identity mismatch")
    bad = [
        relative for relative, digest in manifest["outputs"].items()
        if sha256(path / relative) != digest
    ]
    if bad:
        raise ValueError(f"{arm}: output hash mismatch: {bad}")
    daily = pd.read_csv(path / "daily_ledger.csv")
    if daily.day_index.tolist() != list(range(181)):
        raise ValueError(f"{arm}: expected January 1 through June 30")
    development = daily[daily.day_index >= 31].copy()
    if len(development) != 150:
        raise ValueError(f"{arm}: expected 150 development days")
    return manifest, development, config


def run(args: argparse.Namespace) -> Path:
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    paths = {
        "B0": Path(args.b0).resolve(),
        "Abl-L": Path(args.abl_l).resolve(),
        "Abl-PV": Path(args.abl_pv).resolve(),
        "B1": Path(args.b1).resolve(),
    }
    loaded = {arm: load_run(paths[arm], arm) for arm in ARM_ORDER}
    manifests = {arm: loaded[arm][0] for arm in ARM_ORDER}
    frames = {arm: loaded[arm][1] for arm in ARM_ORDER}
    if len({manifest["git_commit"] for manifest in manifests.values()}) != 1:
        raise ValueError("four arms must use one Git commit")

    # The experiment contract requires identical January predictions and policy.
    January_keys = ("load_b0", "pv_b0")
    reference_forecasts = np.load(paths["B0"] / "forecast_bundle.npz")
    reference_policy = np.load(paths["B0"] / "policy_arrays.npz")
    january_checks = {}
    for arm in ARM_ORDER:
        forecasts = np.load(paths[arm] / "forecast_bundle.npz")
        policy = np.load(paths[arm] / "policy_arrays.npz")
        january_checks[arm] = {
            "forecast_equal": bool(all(
                np.array_equal(forecasts[key][:31], reference_forecasts[key][:31])
                for key in January_keys
            )),
            "policy_equal": bool(all(
                np.allclose(policy[key][:31], reference_policy[key][:31], atol=1e-8)
                for key in ("G", "C", "D", "Emergency", "Spill", "SOC")
            )),
        }
    if not all(
        item["forecast_equal"] and item["policy_equal"]
        for item in january_checks.values()
    ):
        raise ValueError("four arms do not share the same January trajectory")

    data = load_data()
    actual_load = data.load[31:181]
    actual_pv = data.pv[31:181]
    forecast_rows = []
    for arm in ARM_ORDER:
        bundle = np.load(paths[arm] / "forecast_bundle.npz")
        load = bundle["load_b0"] if arm in ("B0", "Abl-PV") else bundle["load_hgb"]
        pv = bundle["pv_b0"] if arm in ("B0", "Abl-L") else bundle["pv_hgb"]
        for target, predicted, actual in (
            ("load", load[31:181], actual_load),
            ("pv", pv[31:181], actual_pv),
        ):
            error = predicted - actual
            forecast_rows.append({
                "arm": arm,
                "model_id": ARM_MODEL_IDS[arm],
                "target": target,
                "n": int(error.size),
                "mae_kw": float(np.mean(np.abs(error))),
                "rmse_kw": float(np.sqrt(np.mean(error ** 2))),
                "bias_kw": float(np.mean(error)),
            })

    baseline = frames["B0"]
    baseline_cash = float(baseline.realized_total_cost_yuan.sum())
    baseline_adjusted = baseline_cash + ASSET_VALUE * (
        6000.0 - float(baseline.actual_end_energy_kwh.iloc[-1])
    )
    baseline_emergency = float(baseline.emergency_kwh.sum())
    baseline_cvar = empirical_cvar95(baseline.realized_total_cost_yuan)
    comparison_rows = []
    bootstrap_rows = []
    passers = []
    for arm in ARM_ORDER:
        frame = frames[arm]
        cash = float(frame.realized_total_cost_yuan.sum())
        end_energy = float(frame.actual_end_energy_kwh.iloc[-1])
        adjusted = cash + ASSET_VALUE * (6000.0 - end_energy)
        emergency = float(frame.emergency_kwh.sum())
        cvar = empirical_cvar95(frame.realized_total_cost_yuan)
        difference = (
            frame.realized_total_cost_yuan.to_numpy(float)
            - baseline.realized_total_cost_yuan.to_numpy(float)
        )
        boot = {}
        for block in (3, 7, 14):
            boot[block] = block_bootstrap(difference, block)
            bootstrap_rows.append({
                "arm": arm,
                "model_id": ARM_MODEL_IDS[arm],
                "block_days": block,
                **boot[block],
            })
        saving = baseline_adjusted - adjusted
        checks = {
            "saving_at_least_0_1pct": (
                arm != "B0" and saving / baseline_adjusted >= 0.001
            ),
            "block14_upper_below_zero": (
                arm != "B0" and boot[14]["upper_95_yuan"] < 0.0
            ),
            "emergency_within_101pct": emergency <= 1.01 * baseline_emergency,
            "daily_cvar95_within_101pct": cvar <= 1.01 * baseline_cvar,
        }
        adopted_eligible = arm != "B0" and all(checks.values())
        if adopted_eligible:
            passers.append((arm, adjusted))
        comparison_rows.append({
            "arm": arm,
            "model_id": ARM_MODEL_IDS[arm],
            "days": len(frame),
            "cash_cost_yuan": cash,
            "end_energy_kwh": end_energy,
            "terminal_adjustment_yuan": adjusted - cash,
            "asset_adjusted_cost_yuan": adjusted,
            "asset_adjusted_saving_vs_b0_yuan": saving,
            "asset_adjusted_saving_vs_b0_fraction": saving / baseline_adjusted,
            "emergency_kwh": emergency,
            "daily_cost_cvar95_yuan": cvar,
            **checks,
            "adoption_eligible": adopted_eligible,
        })

    selected = "B0"
    if passers:
        passers.sort(key=lambda item: (item[1], ARM_ORDER.index(item[0])))
        selected = passers[0][0]
        for arm, adjusted in passers[1:]:
            selected_adjusted = next(v for a, v in passers if a == selected)
            if abs(adjusted - selected_adjusted) / baseline_adjusted <= 0.0005:
                selected = min((selected, arm), key=ARM_ORDER.index)

    comparison = pd.DataFrame(comparison_rows)
    bootstrap = pd.DataFrame(bootstrap_rows)
    combined_daily = pd.concat([
        frames[arm].assign(arm=arm, model_id=ARM_MODEL_IDS[arm])
        for arm in ARM_ORDER
    ], ignore_index=True)
    comparison.to_csv(output / "development_comparison.csv", index=False)
    bootstrap.to_csv(output / "development_bootstrap.csv", index=False)
    combined_daily.to_csv(output / "development_daily_ledger.csv", index=False)
    pd.DataFrame(forecast_rows).to_csv(
        output / "development_forecast_metrics.csv", index=False
    )
    decision = {
        "status": "complete",
        "scope": "2025-02-01 through 2025-06-30 development only",
        "selected_arm": selected,
        "selected_model_id": ARM_MODEL_IDS[selected],
        "predictor_upgrade_adopted": selected != "B0",
        "reason": (
            "At least one fixed challenger passed every predeclared gate."
            if selected != "B0"
            else "No challenger passed every predeclared gate; retain B0."
        ),
        "adoption_rule": {
            "minimum_asset_adjusted_saving_fraction": 0.001,
            "block14_upper_95_must_be_below_yuan": 0.0,
            "maximum_emergency_ratio": 1.01,
            "maximum_daily_cvar95_ratio": 1.01,
            "tie_fraction_of_b0": 0.0005,
            "simplicity_order": list(ARM_ORDER),
            "asset_value_yuan_per_kwh": ASSET_VALUE,
            "bootstrap_seed": SEED,
            "bootstrap_draws": N_BOOTSTRAP,
        },
        "january_checks": january_checks,
    }
    write_json(output / "development_decision.json", decision)
    evidence = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_runs": {
            arm: {
                "path": str(paths[arm]),
                "manifest_sha256": sha256(paths[arm] / "manifest.json"),
                "git_commit": manifests[arm]["git_commit"],
                "summary_sha256": sha256(paths[arm] / "summary.json"),
                "daily_ledger_sha256": sha256(paths[arm] / "daily_ledger.csv"),
            }
            for arm in ARM_ORDER
        },
        "outputs": {
            path.name: sha256(path)
            for path in sorted(output.iterdir())
            if path.is_file()
        },
    }
    write_json(output / "development_evidence_manifest.json", evidence)
    print(json.dumps(decision, ensure_ascii=False, indent=2))
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--b0", required=True)
    parser.add_argument("--abl-l", required=True)
    parser.add_argument("--abl-pv", required=True)
    parser.add_argument("--b1", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
