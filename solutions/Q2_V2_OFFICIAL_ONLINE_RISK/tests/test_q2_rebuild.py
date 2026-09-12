from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np

from q2_model import E_MAX, E_MIN, Q_MAX, build_forecasts, load_data, make_scenarios, settle_causally, two_stage_plan


class Q2RebuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_data()
        cls.load_fc, cls.pv_fc = build_forecasts(cls.data)

    def test_no_future_leakage_by_forecast_definition(self):
        day = 31
        expected = (self.data.load[day - 7] + self.data.load[day - 14]) / 2
        np.testing.assert_allclose(self.load_fc["same_weekday_2w"][day], expected)

    def test_forecast_is_not_actual(self):
        day = 31
        self.assertGreater(np.mean(np.abs(self.load_fc["same_weekday_2w"][day] - self.data.load[day])), 0)
        self.assertGreater(np.mean(np.abs(self.pv_fc["recent_3d"][day] - self.data.pv[day])), 0)

    def test_executor_physics(self):
        day = 31
        g = np.maximum((self.load_fc["same_weekday_2w"][day] - self.pv_fc["recent_3d"][day]) / 6, 0)
        a = settle_causally(g, self.data.load[day], self.data.pv[day], 6000)
        self.assertLess(np.max(np.abs(a["balance_residual"])), 1e-6)
        self.assertGreaterEqual(a["soc"].min(), E_MIN - 1e-8)
        self.assertLessEqual(a["soc"].max(), E_MAX + 1e-8)
        self.assertLessEqual(a["c"].max(), Q_MAX + 1e-8)
        self.assertLessEqual(a["d"].max(), Q_MAX + 1e-8)
        self.assertFalse(np.any((a["c"] > 1e-8) & (a["d"] > 1e-8)))

    def test_two_stage_nonanticipativity_and_no_emergency_charge(self):
        day = 31
        lp, pp = self.load_fc["same_weekday_2w"], self.pv_fc["recent_3d"]
        ls, ps, w = make_scenarios(self.data, lp, pp, day, count=10, window=21)
        g, diag = two_stage_plan(self.data.price, ls, ps, w, 6000, terminal="hard")
        self.assertEqual(g.shape, (144,))
        self.assertEqual(diag["emergency_charge_path_violation"], 0)
        self.assertEqual(diag["recourse_simultaneous_charge_discharge_count"], 0)
        self.assertLess(diag["max_source_pool_residual"], 1e-6)

    def test_completed_run_audit_when_available(self):
        p = Path(__file__).resolve().parents[1] / "results" / "q2_rebuild" / "audit" / "p0_audit.json"
        if not p.exists(): self.skipTest("full run not completed")
        audit = json.loads(p.read_text(encoding="utf-8"))
        for key in ["future_leakage_pass", "forecast_not_actual_pass", "same_executor_all_models",
                    "cross_day_soc_pass", "balance_pass", "soc_residual_pass",
                    "actual_simultaneous_charge_discharge_pass", "m2_emergency_charge_pass"]:
            self.assertTrue(audit[key], key)


if __name__ == "__main__":
    unittest.main()
