# Q2 最终验证摘要

{
  "formal_main_model": "ONLINE-RISK-SP",
  "formal_total_cost_wan": 1380.803333064248,
  "exploratory_best_model": "SP-CVaR tau=0.95 rho=0.05",
  "exploratory_best_cost_wan": 1378.2870206458374,
  "online_adaptive_model_cost_wan": 1380.803333064248,
  "time_alignment_resolved": true,
  "independent_cost_audit_pass": true,
  "detailed_leakage_audit_pass": true,
  "emergency_to_battery_pass": true,
  "physical_audit_pass": true,
  "nonanticipativity_pass": true,
  "terminal_inventory_comparison_complete": true,
  "cvar_scenario_count_stable": true,
  "random_seed_stable": "NOT_APPLICABLE_DETERMINISTIC",
  "calibration_selection_verified": true,
  "calibration_selection_frequency": 0.8387096774193549,
  "post_selection_bias_handled": true,
  "top5_clean_rerun_pass": true,
  "paper_formulas_complete": true,
  "paper_algorithm_complete": true,
  "paper_tables_complete": true,
  "paper_figures_complete": true,
  "q2_frozen": true,
  "decision_reason": "All Q2 V3 correctness, stability, causal-selection, reproducibility, and paper-readiness gates passed.",
  "formal_tau": 0.9,
  "formal_rho": 0.05,
  "formal_gamma": 0.0,
  "formal_scenario_stability": {
    "complete": true,
    "stable": true,
    "cost_min_wan": 1394.836028649821,
    "cost_max_wan": 1396.5406688469554,
    "cost_range_wan": 1.7046401971344949,
    "relative_range": 0.0012213616303834343,
    "counts": [
      50,
      100
    ]
  },
  "exploratory_scenario_stability": {
    "complete": true,
    "stable": true,
    "cost_min_wan": 1385.3159105846894,
    "cost_max_wan": 1388.0340163521585,
    "cost_range_wan": 2.718105767469069,
    "relative_range": 0.001962083699971265,
    "counts": [
      50,
      100,
      150
    ]
  },
  "bootstrap_complete": true,
  "bootstrap_ci_contains_zero": true,
  "best_recency_gamma": 0.03,
  "best_recency_cost_wan": 1377.6559188381466,
  "max_time_mapping_delta_pct": 0.0582218870884034,
  "online_independent_cost_residual_yuan": 3.725290298461914e-09,
  "online_audit_pass": true,
  "online_selection_frequency": {
    "nocvar_g0.05": 72,
    "cvar_t0.95_r0.20_g0.02": 39,
    "cvar_t0.90_r0.05_g0.00": 37,
    "cvar_t0.90_r0.05_g0.05": 36,
    "cvar_t0.90_r0.20_g0.00": 36,
    "cvar_t0.90_r0.05_g0.02": 33,
    "cvar_t0.90_r0.20_g0.05": 24,
    "cvar_t0.95_r0.20_g0.05": 20,
    "cvar_t0.95_r0.05_g0.02": 17,
    "nocvar_g0.02": 14,
    "cvar_t0.90_r0.20_g0.02": 3,
    "nocvar_g0.00": 3
  }
}
