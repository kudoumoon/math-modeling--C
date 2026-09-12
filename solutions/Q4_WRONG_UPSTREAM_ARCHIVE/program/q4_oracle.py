"""Price-information oracle for Q4 validation only.

This program deliberately reveals the target-day actual dynamic prices to the
optimizer while keeping the same causal load/PV forecasts and the same January
warm state.  Its outputs are never written to the official result templates.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

PROGRAM_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROGRAM_DIR))
sys.path.insert(0, str(ROOT / "Q2" / "program"))
sys.path.insert(0, str(ROOT / "Q3" / "v2" / "program"))

import q2_pipeline_v1 as core
import q2_v2_compatible as q2full
import q3_pipeline_v2 as q3p1
import q4_core as q4
import q4_full as full


OUT = ROOT / "Q4" / "result"
TOL = 1e-5


class OracleCurveCache:
    def __init__(self, dataset, actual_price, library) -> None:
        self.dataset = dataset
        self.actual_price = actual_price
        self.library = library
        self.cache: Dict[int, Tuple[np.ndarray, np.ndarray]] = {}

    def get(self, day: int) -> Tuple[np.ndarray, np.ndarray]:
        if day >= full.LAST_DAY:
            raise ValueError("最后一天使用硬终端SOC")
        if day not in self.cache:
            issue = self.dataset.dates[day]
            future = q2full.make_forecast(self.dataset, day + 1, issue, full.COMBO)
            margin, _, _ = q4.causal_margin_60(
                self.dataset, self.library, full.COMBO, issue
            )
            values = []
            for start_soc in q2full.R2_GRID:
                solved = q2full.solve_plan(
                    future.net_kwh + margin,
                    self.actual_price[day + 1],
                    float(start_soc),
                    "hard",
                    hard_anchor=core.INITIAL_SOC_KWH,
                )
                if float(solved["max_residual"]) > TOL:
                    raise AssertionError("Oracle终端价值LP残差超限")
                values.append(float(solved["cash"]))
            grid = np.asarray(q2full.R2_GRID, dtype=float)
            values_array = np.asarray(values, dtype=float)
            slopes = np.diff(values_array) / np.diff(grid)
            if np.max(slopes) > 1e-7 or np.min(np.diff(slopes)) < -1e-7:
                raise AssertionError("Oracle终端价值曲线不满足单调凸性")
            self.cache[day] = grid, values_array
        grid, values = self.cache[day]
        return grid.copy(), values.copy()


def run() -> dict:
    started = time.perf_counter()
    dataset = core.load_dataset()
    actual_price = q4.load_actual_prices(dataset)
    library = q2full.build_forecast_library(dataset, [full.COMBO])
    # Freeze the exact same causal January state used by the official result.
    warm = q4.build_warm_context(30)
    curves = OracleCurveCache(dataset, actual_price, library)

    original_price_builder = q4.build_price_forecast

    def perfect_price_builder(dataset_, actual_price_, target_day, issue_time):
        source_times = dataset_.interval_starts(target_day)
        return q4.PriceForecast(
            target_day=int(target_day),
            issue_time=pd.Timestamp(issue_time),
            values=np.asarray(actual_price_[target_day], dtype=float).copy(),
            source_times=source_times,
            current_actual_step=None,
        )

    q4.build_price_forecast = perfect_price_builder
    try:
        log42, _, _ = full.simulate_q42(
            dataset, actual_price, library, curves, warm
        )
        book = q3p1.load_forecast_book(dataset)
        forecast_cache = full.ReleaseForecastCache(dataset, book, library)
        log43, decisions43, _ = full.simulate_q43(
            dataset, actual_price, library, curves, forecast_cache, warm, "M3"
        )
    finally:
        q4.build_price_forecast = original_price_builder

    audit42 = full.physical_audit(log42, dataset, q43=False)
    audit43 = full.physical_audit(log43, dataset, q43=True)
    if audit42["status"] != "PASS" or audit43["status"] != "PASS":
        raise AssertionError("Oracle物理审计失败")
    summary42 = full.summarize_q42(log42, dataset)
    summary43 = full.summarize_q43(log43, dataset)
    causal = json.loads((OUT / "q4_final_summary.json").read_text(encoding="utf-8"))
    official42 = float(causal["q4_2"]["total_cash_yuan"])
    official43 = float(causal["q4_3"]["M3"]["total_cash_B_yuan"])
    result = {
        "status": "PASS",
        "scope": "price-information upper-bound only; not an admissible policy",
        "same_causal_load_pv_forecasts": True,
        "same_january_warm_state": True,
        "q4_2": {
            **summary42,
            "causal_total_yuan": official42,
            "oracle_saving_yuan": official42 - summary42["total_cash_yuan"],
            "oracle_saving_rate": (official42 - summary42["total_cash_yuan"]) / official42,
        },
        "q4_3_M3": {
            **summary43,
            "causal_total_yuan": official43,
            "oracle_saving_yuan": official43 - summary43["total_cash_B_yuan"],
            "oracle_saving_rate": (official43 - summary43["total_cash_B_yuan"]) / official43,
            "decisions": int(len(decisions43)),
            "accepted": int(decisions43["accepted"].sum()),
        },
        "physical_audits": {"q4_2": audit42, "q4_3_M3": audit43},
        "runtime_seconds": time.perf_counter() - started,
    }
    log42.to_csv(OUT / "q4_2_price_oracle_execution_log.csv", index=False, encoding="utf-8-sig")
    log43.to_csv(OUT / "q4_3_M3_price_oracle_execution_log.csv", index=False, encoding="utf-8-sig")
    (OUT / "q4_price_oracle_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "status": "PASS",
        "q4_2_oracle_total_yuan": summary42["total_cash_yuan"],
        "q4_2_oracle_saving_yuan": result["q4_2"]["oracle_saving_yuan"],
        "q4_3_M3_oracle_total_yuan": summary43["total_cash_B_yuan"],
        "q4_3_M3_oracle_saving_yuan": result["q4_3_M3"]["oracle_saving_yuan"],
        "runtime_seconds": result["runtime_seconds"],
    }, ensure_ascii=False, indent=2), flush=True)
    return result


if __name__ == "__main__":
    run()
