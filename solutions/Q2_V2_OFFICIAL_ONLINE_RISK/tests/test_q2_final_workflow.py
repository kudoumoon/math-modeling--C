from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd

from build_q2_final_validation_v3 import cost_stability
from run_q2_online_selector import candidate_grid, fingerprint


def test_online_candidate_grid_is_unique_and_has_tail_candidates():
    candidates = candidate_grid()
    ids = [item["candidate_id"] for item in candidates]
    assert len(candidates) == 15
    assert len(ids) == len(set(ids))
    assert any(item["rho"] == 0.0 for item in candidates)
    assert any(item["gamma"] == 0.05 for item in candidates)
    assert {item["tau"] for item in candidates if item["rho"] > 0} == {0.90, 0.95}


def test_online_fingerprint_is_order_independent():
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})


def test_cost_stability_requires_large_counts():
    frame = pd.DataFrame({
        "nominal_scenario_count": [10, 20, 30, 50, 100],
        "total_cost_wan": [1398.0, 1398.5, 1397.9, 1398.2, 1398.4],
    })
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "formal_cvar_scenario_stability.csv"
        frame.to_csv(path, index=False)
        result = cost_stability(path, minimum_count=50)
    assert result["complete"] is True
    assert result["stable"] is True
    assert result["counts"] == [50, 100]

