import numpy as np

from forecasting.economic import execute_day, plan_day


def test_planner_and_executor_are_energy_feasible():
    net = np.full(144, 3000.0)
    price = np.linspace(0.4, 1.2, 144)
    q = plan_day(net, price, initial_energy=6000.0)
    result = execute_day(q, net, np.zeros(144), price, initial_energy=6000.0)
    assert len(q) == 144
    assert np.min(q) >= -1e-8
    assert 1200 - 1e-7 <= result.end_energy <= 10800 + 1e-7
    assert np.min(result.emergency) >= -1e-8


def test_emergency_energy_is_charged_at_five_times_price():
    q = np.zeros(144)
    load = np.zeros(144)
    load[0] = 6000.0
    price = np.ones(144)
    result = execute_day(q, load, np.zeros(144), price, initial_energy=1200.0)
    assert np.isclose(result.emergency[0], 1000.0)
    assert np.isclose(result.emergency_cost, 5000.0)
