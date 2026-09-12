# Q2 Final Validation V3 Report

- formal_main_model: ONLINE-RISK-SP
- formal_total_cost_wan: 1380.803333
- exploratory_best_cost_wan: 1378.287021
- online_adaptive_model_cost_wan: 1380.803333064248
- q2_frozen: True
- decision_reason: All Q2 V3 correctness, stability, causal-selection, reproducibility, and paper-readiness gates passed.

## Gate Evidence

- independent_cost_audit_pass: True
- detailed_leakage_audit_pass: True
- physical_audit_pass: True
- terminal_inventory_comparison_complete: True
- cvar_scenario_count_stable: True
- top5_clean_rerun_pass: True
- paper_tables_complete: True
- paper_figures_complete: True

## Required 20 Answers

1. 1398.374935 independent recalculation: PASS.
2. 1378.287021 independent recalculation: PASS.
3. Future leakage: none detected.
4. Emergency-to-battery: zero.
5. First-stage nonanticipativity: PASS.
6. Maximum power-balance residual: 2.27374e-13 kWh.
7. Maximum SOC-recursion residual: 9.09495e-13 kWh.
8. Adopted time interpretation: current/left mapping, because dual mapping is robust below 0.1%.
9. Maximum alternative-mapping cost change: 0.058222%.
10. Terminal inventory-adjusted ranking is reported in terminal_fairness_v2.csv.
11. Formal tau=.90 rho=.05 S=50/100: {"complete": true, "stable": true, "cost_min_wan": 1394.836028649821, "cost_max_wan": 1396.5406688469554, "cost_range_wan": 1.7046401971344949, "relative_range": 0.0012213616303834343, "counts": [50, 100]}.
12. Exploratory tau=.95 rho=.05 large-S: {"complete": true, "stable": true, "cost_min_wan": 1385.3159105846894, "cost_max_wan": 1388.0340163521585, "cost_range_wan": 2.718105767469069, "relative_range": 0.001962083699971265, "counts": [50, 100, 150]}.
13. Random-seed stability: NOT_APPLICABLE because scenario selection is deterministic.
14. Best post-hoc recency gamma: 0.03 at 1377.655919 万元.
15. January calibration evidence: True.
16. Calibration selection frequency: 0.8387096774193549.
17. Strict online selector cost: 1380.803333064248.
18. Bootstrap interval contains zero: True.
19. Final formal model: ONLINE-RISK-SP at 1380.803333 万元.
20. Q2 unconditional freeze: True.
