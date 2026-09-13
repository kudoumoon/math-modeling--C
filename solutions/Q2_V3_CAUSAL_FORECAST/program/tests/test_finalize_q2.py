from __future__ import annotations

import pandas as pd

import numpy as np
import pytest

from finalize_q2 import audit_soc_boundaries, emergency_events, natural_day_ledger, storage_blocks


def _ledger() -> pd.DataFrame:
    rows = []
    start = pd.Timestamp("2025-02-01 00:10")
    for slot in range(144):
        rows.append({
            "plan_day": "2025-02-01",
            "time_index": slot,
            "interval_start": start + pd.Timedelta(minutes=10 * slot),
            "interval_end": start + pd.Timedelta(minutes=10 * (slot + 1)),
            "charge_kwh": 1.0,
            "discharge_kwh": 2.0,
            "emergency_kwh": 3.0 if slot in (1, 2, 4) else 0.0,
            "actual_soc_before_kwh": 6000.0 + slot,
            "actual_soc_after_kwh": 6001.0 + slot,
        })
    return pd.DataFrame(rows)


def test_emergency_events_merge_only_contiguous_positive_intervals():
    events = emergency_events(_ledger())
    assert len(events) == 2
    assert events["emergency_kwh"].tolist() == [6.0, 3.0]
    assert events["interval_count"].tolist() == [2, 1]
    assert events.iloc[0]["time_period"] == "00:20-00:40"


def test_storage_blocks_have_six_complete_four_hour_groups():
    blocks = storage_blocks(_ledger())
    assert len(blocks) == 6
    assert blocks["charge_kwh"].tolist() == [24.0] * 6
    assert blocks["discharge_kwh"].tolist() == [48.0] * 6
    assert blocks.iloc[0]["time_period"] == "0:00-4:00"
    assert blocks.iloc[-1]["time_period"] == "20:00-24:00"
    assert blocks.iloc[0]["soc_0000_kwh"] == 6000.0
    assert blocks.iloc[-1]["soc_2400_kwh"] == 6144.0


def test_natural_day_bridge_uses_previous_plan_midnight_slot():
    arrays = {
        key: np.zeros((365, 144))
        for key in (
            "G", "C", "D", "CommandedC", "CommandedD", "Emergency", "Spill"
        )
    }
    arrays["SOC"] = np.zeros((365, 145))
    arrays["G"][30, 143] = 30143.0
    arrays["G"][31, 0] = 31000.0
    arrays["G"][31, 142] = 31142.0
    bridged = natural_day_ledger(arrays, pd.date_range("2025-01-01", periods=365))
    first = bridged.loc[bridged["natural_day"] == "2025-02-01"]
    assert len(first) == 144
    assert first.iloc[0]["planned_grid_kwh"] == 30143.0
    assert first.iloc[0]["source_plan_day"] == "2025-01-31"
    assert first.iloc[1]["planned_grid_kwh"] == 31000.0
    assert first.iloc[-1]["planned_grid_kwh"] == 31142.0


def test_only_declared_reset_boundary_is_exempted():
    soc = np.full((365, 145), 6000.0)
    soc[:31] = 5000.0
    days = np.arange(365)
    assert not audit_soc_boundaries(soc, days, compatibility_reset=False)["passed"]
    audited = audit_soc_boundaries(soc, days, compatibility_reset=True)
    assert audited["passed"]
    assert audited["declared_reset_jump_kwh"] == 1000.0
    assert audited["continuous_boundaries_checked"] == 363
    soc[32, 0] += 1.0
    assert not audit_soc_boundaries(soc, days, compatibility_reset=True)["passed"]


def test_reset_target_and_finite_boundaries_remain_mandatory():
    soc = np.full((365, 145), 6000.0)
    soc[31, 0] = 5900.0
    assert not audit_soc_boundaries(soc, np.arange(365), compatibility_reset=True)["passed"]
    soc[31, 0] = np.nan
    assert not audit_soc_boundaries(soc, np.arange(365), compatibility_reset=True)["passed"]


def test_storage_blocks_reject_missing_or_duplicate_slots():
    with pytest.raises(AssertionError):
        storage_blocks(_ledger().iloc[:-1])
    with pytest.raises(AssertionError):
        storage_blocks(pd.concat([_ledger(), _ledger().iloc[:1]]))


def test_storage_uses_natural_midnight_bridge_without_changing_plans():
    arrays = {key: np.ones((365, 144)) for key in
              ("G", "C", "D", "CommandedC", "CommandedD", "Emergency", "Spill")}
    arrays["SOC"] = np.full((365, 145), 6000.0)
    arrays["C"][30, 143] = 9.0
    arrays["C"][31, 23] = 99.0
    bridge = natural_day_ledger(arrays, pd.date_range("2025-01-01", periods=365))
    blocks = storage_blocks(bridge)
    assert blocks.iloc[0]["charge_kwh"] == 32.0
    assert blocks.iloc[1]["charge_kwh"] == 122.0
    assert arrays["C"][31, 23] == 99.0
