from __future__ import annotations

import pandas as pd

import numpy as np

from finalize_q2 import emergency_events, natural_day_ledger, storage_blocks


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
