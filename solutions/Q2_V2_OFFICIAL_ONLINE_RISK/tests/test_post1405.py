import unittest

import numpy as np

from q2_model import (
    E_INIT, Q2Data, deterministic_plan, run_stochastic_policy,
    settle_causally, two_stage_plan,
)
from post1405_core import (
    block_bootstrap_ci,
    format_result_interval,
    scenario_moment_row,
    select_similar_residual_days,
)


class Post1405CoreTests(unittest.TestCase):
    def test_time_mapping_matches_frozen_q2_convention(self):
        self.assertEqual(format_result_interval(0), "0:10-0:20")
        self.assertEqual(format_result_interval(142), "23:50-0:00+1")
        self.assertEqual(format_result_interval(143), "0:00-0:10+1")

    def test_block_bootstrap_is_deterministic_and_uses_week_blocks(self):
        values = np.arange(21, dtype=float) - 10.0
        first = block_bootstrap_ci(values, n_bootstrap=200, block_length=7, seed=17)
        second = block_bootstrap_ci(values, n_bootstrap=200, block_length=7, seed=17)
        self.assertEqual(first, second)
        self.assertEqual(first["block_length_days"], 7)
        self.assertEqual(first["n_bootstrap"], 200)

    def test_similarity_selection_uses_only_past_days(self):
        features = np.array([[0.0], [1.0], [2.0], [100.0], [3.0]])
        chosen = select_similar_residual_days(features, day=4, window=10, count=2)
        self.assertEqual(chosen.tolist(), [2, 1])
        self.assertTrue(np.all(chosen < 4))

    def test_scenario_audit_reports_required_moments(self):
        historical = np.array([[0.0, 1.0, 2.0], [1.0, 2.0, 3.0]])
        generated = historical.copy()
        row = scenario_moment_row("load", historical, generated)
        self.assertAlmostEqual(row["history_mean"], row["scenario_mean"])
        self.assertAlmostEqual(row["history_q90"], row["scenario_q90"])
        self.assertIn("history_lag1_corr", row)

    def test_deterministic_plan_supports_one_day_terminal_target(self):
        price = np.ones(144)
        load = np.full(144, 1000.0)
        pv = np.zeros(144)
        plan = deterministic_plan(price, load, pv, E_INIT, cyclic=False, terminal_target=E_INIT)
        actual = settle_causally(plan, load, pv, E_INIT)
        self.assertAlmostEqual(actual["soc"][-1], E_INIT, places=5)

    def test_two_stage_hard_terminal_accepts_common_target(self):
        price = np.ones(144)
        load = np.full((1, 144), 1000.0)
        pv = np.zeros((1, 144))
        plan, diagnostics = two_stage_plan(
            price, load, pv, np.ones(1), E_INIT,
            terminal="hard", terminal_target=5000.0,
        )
        actual = settle_causally(plan, load[0], pv[0], E_INIT)
        self.assertAlmostEqual(actual["soc"][-1], 5000.0, places=5)
        self.assertEqual(diagnostics["terminal_target"], 5000.0)

    def test_two_stage_can_evaluate_a_fixed_first_stage_plan(self):
        price = np.ones(144)
        load = np.full((2, 144), 1000.0)
        pv = np.zeros((2, 144))
        fixed = np.full(144, 1000.0 / 6.0)
        plan, diagnostics = two_stage_plan(
            price, load, pv, np.full(2, 0.5), E_INIT,
            terminal="hard", fixed_g=fixed,
        )
        np.testing.assert_allclose(plan, fixed, atol=1e-7)
        self.assertTrue(diagnostics["fixed_first_stage"])

    def test_two_stage_cvar_extension_is_feasible_and_reported(self):
        price = np.ones(144)
        load = np.vstack([np.full(144, 1000.0), np.full(144, 2000.0)])
        pv = np.zeros_like(load)
        plan, diagnostics = two_stage_plan(
            price, load, pv, np.full(2, 0.5), E_INIT,
            terminal="hard", cvar_beta=0.9, cvar_weight=0.1,
        )
        self.assertEqual(plan.shape, (144,))
        self.assertEqual(diagnostics["cvar_beta"], 0.9)
        self.assertEqual(diagnostics["cvar_weight"], 0.1)

    def test_stochastic_runner_accepts_causal_scenario_factory(self):
        load = np.full((365, 144), 1000.0)
        pv = np.zeros((365, 144))
        data = Q2Data(
            dates=np.arange("2025-01-01", "2026-01-01", dtype="datetime64[D]"),
            price=np.ones(144), load=load, pv=pv,
            source_labels=[str(i) for i in range(144)],
        )
        calls = []

        def factory(data_arg, load_pred, pv_pred, day, count, window):
            calls.append(day)
            return load_pred[day][None], pv_pred[day][None], np.ones(1)

        result = run_stochastic_policy(
            data, load, pv, days=np.array([31]), scenario_count=1,
            terminal="hard", scenario_factory=factory,
        )
        self.assertEqual(calls, [31])
        self.assertEqual(result["days"], 1)


if __name__ == "__main__":
    unittest.main()
