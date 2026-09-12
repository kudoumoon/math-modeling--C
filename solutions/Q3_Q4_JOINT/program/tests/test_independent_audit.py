"""Real existing Q2 transactions test rejection of tampered joint evidence."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_ledger import ROOT, audit


@pytest.mark.parametrize("mutation,failed_check", [
    ("none", None),
    ("cash", "total_cost_yuan"),
    ("q0", "q0_matches_Q2_G"),
    ("clock", "interval_start_mapping_A"),
])
def test_existing_transactions_and_tampering(tmp_path, mutation, failed_check):
    frame = pd.read_csv(ROOT / "solutions/Q3_Q4_JOINT/results/q2_provisional/interval_ledger.csv")
    frame = frame.rename(columns={"actual_soc_before_kwh": "soc_before_kwh", "actual_soc_after_kwh": "soc_after_kwh", "plan_cost_yuan": "base_cost_yuan"})
    frame["q0_kwh"] = frame.planned_grid_kwh
    frame["qfinal_kwh"] = frame.planned_grid_kwh
    frame["load_actual_kwh"] = frame.load_actual_kw / 6
    frame["pv_actual_kwh"] = frame.pv_actual_kw / 6
    frame["u_kwh"] = frame["r_kwh"] = 0.
    frame["up_cost_yuan"] = frame["down_cost_yuan"] = 0.
    frame["total_cost_yuan"] = frame.base_cost_yuan + frame.emergency_cost_yuan
    frame["confirmation_count"] = 0
    frame["settlement"] = "A"
    if mutation == "cash":
        frame.loc[0, "total_cost_yuan"] += 1.
    elif mutation == "q0":
        frame.loc[0, "q0_kwh"] += 1.
    elif mutation == "clock":
        frame.loc[143, "interval_start"] = "2025-02-01 00:00:00"
    ledger = tmp_path / "ledger.csv"
    frame.to_csv(ledger, index=False)
    result = audit(ledger, "Q3")
    assert result["passed"] is (failed_check is None)
    if failed_check is not None:
        assert result["checks"][failed_check] is False
