from __future__ import annotations

import numpy as np

from evaluate_development import block_bootstrap, empirical_cvar95


def test_bootstrap_is_deterministic():
    values = np.arange(30, dtype=float) - 15
    assert block_bootstrap(values, 7) == block_bootstrap(values, 7)


def test_empirical_cvar_uses_worst_five_percent():
    values = __import__("pandas").Series(np.arange(100, dtype=float))
    assert empirical_cvar95(values) == np.mean([95, 96, 97, 98, 99])
