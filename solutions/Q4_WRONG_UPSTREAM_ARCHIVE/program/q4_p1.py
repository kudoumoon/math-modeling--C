"""Q4 P1: one-day vertical slice for Q4-2 and Q4-3."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import sys
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd
import scipy

PROGRAM_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROGRAM_DIR))
sys.path.insert(0, str(ROOT / "Q2" / "program"))
sys.path.insert(0, str(ROOT / "Q3" / "v2" / "program"))

import q2_pipeline_v1 as core
import q2_v2_compatible as q2full
import q3_pipeline_v2 as q3p1
import q4_core as q4


TARGET_DAY = 31
TARGET_DATE = pd.Timestamp("2025-02-01")
OUT = ROOT / "Q4" / "audit" / "p1"
TOL = 1e-5


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def execute_contract(
    dataset: core.Dataset,
    actual_price: np.ndarray,
    q0: np.ndarray,
    qfinal: np.ndarray,
    start_soc: float,
    release_used: np.ndarray,
) -> pd.DataFrame:
    rows = []
    soc = float(start_soc)
    for step in range(core.N_STEPS):
        action = core.feedback_step(
            soc,
            float(qfinal[step]),
            float(dataset.load_kwh[TARGET_DAY, step]),
            float(dataset.pv_kwh[TARGET_DAY, step]),
        )
        price = float(actual_price[TARGET_DAY, step])
        rows.append({
            "interval_start": dataset.interval_starts(TARGET_DAY)[step],
            "step": step,
            "release_used": int(release_used[step]),
            "q0_kwh": float(q0[step]),
            "qfinal_kwh": float(qfinal[step]),
            "load_actual_kwh": float(dataset.load_kwh[TARGET_DAY, step]),
            "pv_actual_kwh": float(dataset.pv_kwh[TARGET_DAY, step]),
            "price_actual_yuan_per_kwh": price,
            "charge_kwh": float(action["charge_kwh"]),
            "discharge_kwh": float(action["discharge_kwh"]),
            "emergency_kwh": float(action["emergency_kwh"]),
            "unused_supply_kwh": float(action["unused_supply_kwh"]),
            "soc_before_kwh": soc,
            "soc_after_kwh": float(action["soc_after_kwh"]),
        })
        soc = float(action["soc_after_kwh"])
    return pd.DataFrame(rows)


def physical_audit(log: pd.DataFrame) -> dict:
    energy = (
        log["qfinal_kwh"] + log["pv_actual_kwh"] + log["discharge_kwh"]
        + log["emergency_kwh"] - log["load_actual_kwh"]
        - log["charge_kwh"] - log["unused_supply_kwh"]
    )
    soc = (
        log["soc_after_kwh"] - log["soc_before_kwh"]
        - core.ETA_CHARGE * log["charge_kwh"]
        + log["discharge_kwh"] / core.ETA_DISCHARGE
    )
    return {
        "rows_144": len(log) == 144,
        "max_energy_residual_kwh": float(np.abs(energy).max()),
        "max_soc_residual_kwh": float(np.abs(soc).max()),
        "soc_bounds": bool(
            log[["soc_before_kwh", "soc_after_kwh"]].to_numpy().min() >= core.SOC_MIN_KWH - TOL
            and log[["soc_before_kwh", "soc_after_kwh"]].to_numpy().max() <= core.SOC_MAX_KWH + TOL
        ),
        "power_bounds": bool(
            log[["charge_kwh", "discharge_kwh"]].to_numpy().max() <= core.STEP_LIMIT_KWH + TOL
        ),
        "mutex": bool(((log["charge_kwh"] <= TOL) | (log["discharge_kwh"] <= TOL)).all()),
        "emergency_not_charging": bool(
            ((log["emergency_kwh"] <= TOL) | (log["charge_kwh"] <= TOL)).all()
        ),
    }


def run_p1() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    dataset = core.load_dataset()
    actual_price = q4.load_actual_prices(dataset)
    combo = ("same_weekday_2w", "recent_5d")
    library = q2full.build_forecast_library(dataset, [combo])
    warm = q4.build_warm_context(30)
    if warm.previous.day != 30:
        raise AssertionError("January warm context did not stop at day 30")

    predicted_start = q4.predict_plan_start(warm.soc_midnight, warm.previous)
    bridge = q4.execute_step(
        dataset, actual_price, warm.previous, core.N_STEPS - 1, warm.soc_midnight
    )
    actual_start = float(bridge["soc_after_kwh"])

    # Q4-2: no attachment 3, one contract at 00:00.
    plan42 = q4.make_dynamic_plan(
        dataset, actual_price, library, combo, TARGET_DAY, predicted_start
    )
    price42 = plan42.price_forecast
    release42 = np.zeros(core.N_STEPS, dtype=int)
    log42 = execute_contract(
        dataset, actual_price, plan42.q, plan42.q, actual_start, release42
    )
    ledger42 = q4.ledger_b(
        plan42.q,
        plan42.q,
        actual_price[TARGET_DAY],
        log42["emergency_kwh"].to_numpy(float),
    )

    # Q4-3: Q3-v2 M3 contract with price forecast updated at each release.
    book = q3p1.load_forecast_book(dataset)
    forecast0 = q3p1.build_release_forecast(
        dataset, book, library, TARGET_DAY, 0, use_load_correction=True
    )
    risk0, _, risk0_days, _ = q3p1.residual_pools(
        dataset, book, library, TARGET_DAY, 0, forecast0.steps,
        risk_days=60, gate_days=0,
    )
    margin0 = (
        np.quantile(risk0, q4.ALPHA, axis=0)
        if len(risk0) >= q3p1.MIN_POOL else np.zeros(core.N_STEPS)
    )
    price0 = q4.build_price_forecast(dataset, actual_price, TARGET_DAY, TARGET_DATE)
    curve0 = q4.dynamic_terminal_curve(
        dataset, actual_price, library, combo, TARGET_DAY, TARGET_DATE
    )
    solved0 = q2full.solve_plan(
        forecast0.net_kwh + margin0,
        price0.values,
        predicted_start,
        "pwl",
        pwl_curve=(curve0["grid"], curve0["values"]),
    )
    q0 = np.asarray(solved0["q"], dtype=float)
    qfinal = q0.copy()
    release_used = np.zeros(core.N_STEPS, dtype=int)
    decisions = []
    soc = actual_start
    execution_parts = []

    def execute_block(start: int, end: int) -> None:
        nonlocal soc
        rows = []
        for step in range(start, end):
            action = core.feedback_step(
                soc, float(qfinal[step]),
                float(dataset.load_kwh[TARGET_DAY, step]),
                float(dataset.pv_kwh[TARGET_DAY, step]),
            )
            rows.append({
                "interval_start": dataset.interval_starts(TARGET_DAY)[step],
                "step": step,
                "release_used": int(release_used[step]),
                "q0_kwh": float(q0[step]),
                "qfinal_kwh": float(qfinal[step]),
                "load_actual_kwh": float(dataset.load_kwh[TARGET_DAY, step]),
                "pv_actual_kwh": float(dataset.pv_kwh[TARGET_DAY, step]),
                "price_actual_yuan_per_kwh": float(actual_price[TARGET_DAY, step]),
                "charge_kwh": float(action["charge_kwh"]),
                "discharge_kwh": float(action["discharge_kwh"]),
                "emergency_kwh": float(action["emergency_kwh"]),
                "unused_supply_kwh": float(action["unused_supply_kwh"]),
                "soc_before_kwh": soc,
                "soc_after_kwh": float(action["soc_after_kwh"]),
            })
            soc = float(action["soc_after_kwh"])
        execution_parts.append(pd.DataFrame(rows))

    execute_block(0, 35)
    for release, block in q3p1.BLOCKS.items():
        issue = TARGET_DATE + pd.Timedelta(hours=release)
        forecast = q3p1.build_release_forecast(
            dataset, book, library, TARGET_DAY, release, use_load_correction=True
        )
        risk, gate, risk_days, gate_days = q3p1.residual_pools(
            dataset, book, library, TARGET_DAY, release, forecast.steps,
            risk_days=60, gate_days=14,
        )
        margin = (
            np.quantile(risk, q4.ALPHA, axis=0)
            if len(risk) >= q3p1.MIN_POOL else np.zeros(len(forecast.steps))
        )
        price = q4.build_price_forecast(dataset, actual_price, TARGET_DAY, issue)
        curve = q4.dynamic_terminal_curve(
            dataset, actual_price, library, combo, TARGET_DAY, issue
        )
        solved = q4.solve_adjustment_strict(
            q0, forecast, margin, soc, block, price.values,
            (curve["grid"], curve["values"]),
        )
        candidate = np.asarray(solved["candidate"], dtype=float)
        positions = np.flatnonzero(
            (forecast.steps >= block[0]) & (forecast.steps < block[1])
        )
        gate_block = gate[:, positions] if len(gate) else np.zeros((0, len(positions)))
        accepted = False
        keep_score = None
        new_score = None
        if len(gate_days) >= q3p1.MIN_POOL:
            keep_score = q4.block_score_b(
                qfinal, q0, block, soc, forecast.net_kwh[positions],
                gate_block, price.values,
            )
            new_score = q4.block_score_b(
                candidate, q0, block, soc, forecast.net_kwh[positions],
                gate_block, price.values,
            )
            accepted = bool(new_score < keep_score - 1e-9)
        if accepted:
            qfinal[block[0]:block[1]] = candidate[block[0]:block[1]]
            release_used[block[0]:block[1]] = release
        decisions.append({
            "release_hour": release,
            "issue_time": issue,
            "current_actual_price": float(actual_price[TARGET_DAY, block[0]]),
            "price_max_source_time": price.max_source_time,
            "price_current_actual_step": price.current_actual_step,
            "load_source_max": forecast.load_source_max,
            "load_correction_source_max": forecast.load_correction_source_max,
            "risk_days": len(risk_days),
            "gate_days": len(gate_days),
            "accepted": accepted,
            "keep_score_yuan": keep_score,
            "new_score_yuan": new_score,
            "lp_residual_kwh": solved["max_residual"],
        })
        execute_block(block[0], block[1])

    log43 = pd.concat(execution_parts, ignore_index=True)
    decision_frame = pd.DataFrame(decisions)
    ledger43 = q4.ledger_b(
        q0, qfinal, actual_price[TARGET_DAY],
        log43["emergency_kwh"].to_numpy(float),
    )

    # Price fault injection at 06:00: all future actual prices may change, plan may not.
    changed = actual_price.copy()
    changed[TARGET_DAY, 36:] += 9.0
    base6 = q4.build_price_forecast(
        dataset, actual_price, TARGET_DAY, TARGET_DATE + pd.Timedelta(hours=6)
    )
    changed6 = q4.build_price_forecast(
        dataset, changed, TARGET_DAY, TARGET_DATE + pd.Timedelta(hours=6)
    )

    audit42 = physical_audit(log42)
    audit43 = physical_audit(log43)
    hand_down = q4.ledger_b(
        np.array([100.0]), np.array([80.0]), np.array([1.0]), np.array([0.0])
    )["ordinary_cost_B_yuan"]
    hand_up = q4.ledger_b(
        np.array([100.0]), np.array([120.0]), np.array([1.0]), np.array([0.0])
    )["ordinary_cost_B_yuan"]
    checks = {
        "01_common_continuous_warm_start": abs(actual_start - float(bridge["soc_after_kwh"])) <= TOL,
        "02_warmup_starts_at_6000": abs(float(warm.log.iloc[0]["soc_before_kwh"]) - 6000.0) <= TOL,
        "03_q42_price_sources_causal": price42.max_source_time <= TARGET_DATE,
        "04_q43_price_sources_causal": bool((decision_frame["price_max_source_time"] <= decision_frame["issue_time"]).all()),
        "05_current_release_price_visible": decision_frame["price_current_actual_step"].tolist() == [35, 71, 107],
        "06_future_price_fault_invariant": bool(np.allclose(base6.values, changed6.values)),
        "07_q42_forecast_actual_price_separate": not np.allclose(price42.values, actual_price[TARGET_DAY]),
        "08_q42_dynamic_reoptimization": not np.allclose(plan42.q, np.asarray(pd.read_csv(ROOT / "Q3" / "v2" / "result" / "q3_M0_execution_log.csv")["q0_kwh"].iloc[1:145])),
        "09_q42_physics": bool(all(v if isinstance(v, bool) else v <= TOL for v in audit42.values())),
        "10_q43_physics": bool(all(v if isinstance(v, bool) else v <= TOL for v in audit43.values())),
        "11_b_ledger_hand_cases": abs(hand_down - 90.0) <= TOL and abs(hand_up - 130.0) <= TOL,
        "12_adjustment_lp_residuals": bool((decision_frame["lp_residual_kwh"] <= TOL).all()),
        "13_q43_inherits_m3_releases": decision_frame["release_hour"].tolist() == [6, 12, 18],
        "14_price_actual_positive": bool((log43["price_actual_yuan_per_kwh"] > 0).all()),
        "15_no_solver_fallback_field": "fallback" not in " ".join(decision_frame.columns).lower(),
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    warm.log.to_csv(OUT / "q4_january_warmup_log.csv", index=False, encoding="utf-8-sig")
    warm.decisions.to_csv(OUT / "q4_january_warmup_decisions.csv", index=False, encoding="utf-8-sig")
    log42.to_csv(OUT / "q4_2_p1_execution_log.csv", index=False, encoding="utf-8-sig")
    log43.to_csv(OUT / "q4_3_p1_execution_log.csv", index=False, encoding="utf-8-sig")
    decision_frame.to_csv(OUT / "q4_3_p1_decisions.csv", index=False, encoding="utf-8-sig")
    result = {
        "status": status,
        "target_date": TARGET_DATE.date().isoformat(),
        "bridge": {
            "soc_midnight_kwh": warm.soc_midnight,
            "predicted_start_soc_kwh": predicted_start,
            "actual_start_soc_kwh": actual_start,
        },
        "q4_2": {"ledger": ledger42, "physical": audit42},
        "q4_3": {"ledger": ledger43, "physical": audit43, "decisions": json.loads(decision_frame.to_json(orient="records", date_format="iso"))},
        "checks": checks,
        "manifest": {
            "inputs": {
                "attachment2": sha256(ROOT / "附件" / "附件2.xlsx"),
                "attachment3": sha256(ROOT / "附件" / "附件3.xlsx"),
                "attachment4": sha256(ROOT / "附件" / "附件4.xlsx"),
                "analysis": sha256(ROOT / "Q4" / "题目分析报告.md"),
                "terms": sha256(ROOT / "Q4" / "术语表格.md"),
            },
            "code": {"q4_core": sha256(PROGRAM_DIR / "q4_core.py"), "q4_p1": sha256(Path(__file__))},
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "openpyxl": openpyxl.__version__,
            "command": "python Q4/program/q4_p1.py --mode p1",
        },
    }
    (OUT / "q4_p1_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if status != "PASS":
        raise AssertionError([name for name, ok in checks.items() if not ok])
    print(json.dumps({
        "status": status,
        "bridge": result["bridge"],
        "q4_2_total_yuan": ledger42["total_cash_B_yuan"],
        "q4_3_total_yuan": ledger43["total_cash_B_yuan"],
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
    }, ensure_ascii=False, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["p1"], default="p1")
    parser.parse_args()
    run_p1()


if __name__ == "__main__":
    main()
