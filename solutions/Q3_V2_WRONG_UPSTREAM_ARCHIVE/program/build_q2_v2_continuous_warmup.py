"""Build the continuous Jan-1 to Feb-1 SOC bridge for Q3 v2.

This is intentionally a small, deterministic bridge run.  It uses the Q2 v2
point-forecast names and the project's causal LP engine, but it does not claim
to reproduce the 334-day online selector result.  Its only purpose is to
replace the forbidden Feb-1 SOC reset with a traceable continuous state.
"""

from pathlib import Path
import sys

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "Q2" / "program"))

import q2_pipeline_v1 as core
import q2_v2_compatible as q2full


def main() -> None:
    dataset = core.load_dataset()
    combo = ("same_weekday_2w", "recent_5d")
    library = q2full.build_forecast_library(dataset, [combo])
    cfg = q2full.StrategyConfig("Q2v2_continuous_warmup", combo[0], combo[1], 0.65, "pwl")
    log, decisions, _ = q2full.simulate(
        dataset, 0, 30, cfg, library, r2_anchor=6000.0
    )
    out = ROOT / "Q3" / "v2" / "result"
    out.mkdir(parents=True, exist_ok=True)
    log.to_csv(out / "q2_v2_continuous_warmup_log.csv", index=False, encoding="utf-8-sig")
    decisions.to_csv(out / "q2_v2_continuous_warmup_decisions.csv", index=False, encoding="utf-8-sig")
    row_prev = log.loc[log["interval_start"] == pd.Timestamp("2025-01-31 23:50")].iloc[0]
    row_bridge = log.loc[log["interval_start"] == pd.Timestamp("2025-02-01 00:00")].iloc[0]
    assert abs(float(row_prev["soc_after_kwh"]) - float(row_bridge["soc_before_kwh"])) <= 1e-8
    print({
        "rows": int(len(log)),
        "jan31_2350_soc_after": float(row_prev["soc_after_kwh"]),
        "feb1_0000_soc_before": float(row_bridge["soc_before_kwh"]),
        "feb1_0000_plan_grid_kwh": float(row_bridge["plan_grid_kwh"]),
        "feb1_0000_load_forecast_kwh": float(row_bridge["load_forecast_kwh"]),
        "feb1_0000_pv_forecast_kwh": float(row_bridge["pv_forecast_kwh"]),
    })


if __name__ == "__main__":
    main()
