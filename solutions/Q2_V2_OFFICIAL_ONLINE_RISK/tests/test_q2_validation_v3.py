import numpy as np

from q2_validation_v3 import (
    inventory_adjusted_cost,
    physical_audit,
    recompute_cost,
    shift_right_endpoint_to_left_slots,
    solve_empirical_cvar,
)


def test_recompute_cost_uses_only_raw_grid_emergency_and_price():
    grid = np.array([[1.0, 2.0], [3.0, 4.0]])
    emergency = np.array([[0.0, 1.0], [2.0, 0.0]])
    price = np.array([10.0, 20.0])
    result = recompute_cost(grid, emergency, price)
    assert result["plan_cost_yuan"] == 160.0
    assert result["emergency_cost_yuan"] == 200.0
    assert result["total_cost_yuan"] == 360.0


def test_cvar_epigraph_matches_hand_calculation_at_tau_080():
    costs = np.array([10.0, 20.0, 30.0, 40.0, 100.0])
    result = solve_empirical_cvar(costs, np.full(5, 0.2), tau=0.8)
    assert abs(result["cvar"] - 100.0) < 1e-8
    assert abs(result["z"] - 40.0) < 1e-8 or abs(result["z"] - 100.0) < 1e-8
    assert np.max(np.abs(result["u"] - np.maximum(costs - result["z"], 0.0))) < 1e-8


def test_cvar_epigraph_matches_top_two_mean_at_tau_060():
    costs = np.array([10.0, 20.0, 30.0, 40.0, 100.0])
    result = solve_empirical_cvar(costs, np.full(5, 0.2), tau=0.6)
    assert abs(result["cvar"] - 70.0) < 1e-8


def test_cvar_rejects_non_normalized_probabilities():
    try:
        solve_empirical_cvar(np.array([1.0, 2.0]), np.array([0.4, 0.4]), tau=0.9)
    except ValueError as exc:
        assert "sum" in str(exc)
    else:
        raise AssertionError("non-normalized weights must be rejected")


def test_inventory_adjustment_values_missing_terminal_energy_consistently():
    assert inventory_adjusted_cost(1000.0, 5000.0, target_soc=6000.0, value=0.5) == 1500.0
    assert inventory_adjusted_cost(1000.0, 7000.0, target_soc=6000.0, value=0.5) == 500.0


def test_physical_audit_returns_numeric_evidence():
    load = np.array([[12.0]])
    pv = np.array([[0.0]])
    grid = np.array([[2.0]])
    charge = np.array([[0.0]])
    discharge = np.array([[0.0]])
    emergency = np.array([[0.0]])
    spill = np.array([[0.0]])
    soc = np.array([[6000.0, 6000.0]])
    out = physical_audit(grid, charge, discharge, emergency, spill, soc, load, pv)
    assert out["max_balance_residual_kwh"] == 0.0
    assert out["max_soc_recursion_residual_kwh"] == 0.0
    assert out["emergency_to_battery_energy_kwh"] == 0.0
    assert out["simultaneous_charge_discharge_count"] == 0


def test_right_endpoint_values_are_rotated_to_left_labeled_slots():
    raw = np.array([10.0, 20.0, 30.0, 40.0])
    np.testing.assert_array_equal(
        shift_right_endpoint_to_left_slots(raw),
        np.array([20.0, 30.0, 40.0, 10.0]),
    )
