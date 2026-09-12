# Q2 伪代码

```text
for day in Feb..Dec:
    forecast = causal_forecast(history[:day])
    scenarios = whole_day_residual_scenarios(history[:day], forecast)
    G = solve_common_first_stage_SP(scenarios, actual_SOC, risk_config)
    actual = sequential_settlement(G, actual_load[day], actual_PV[day], actual_SOC)
    actual_SOC = actual.end_SOC

for day in Feb..Dec:
    for candidate in finite_candidate_set:
        candidate_plan[candidate] = solve_from_same_actual_SOC(candidate)
    selected = lowest_mean_prior_realized_cost(candidate_history)
    apply(candidate_plan[selected])
    append_today_realized_cost_to_candidate_history()
```
