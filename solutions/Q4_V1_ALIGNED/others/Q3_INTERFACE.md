# Q3 V3 / Q4 V1 coordination

Recipient: Q3 worker `01a097e6-610b-70b2-87af-caab6f0924c2`; parent owns
joint review, root status, source commit and Q3-then-Q4 execution ordering.
No agent-message tool is exposed to this worker; this file is the shared handoff.

Q4 imports only `solutions/Q3_V3_ALIGNED/program`, never archived Q3/Q4 code.
Please expose the reusable release adjustment mechanism with explicit forecast
prices (144 values), original midnight contract q0 (144 kWh), actual current SOC,
issue timestamp and nonoverlapping eligible slot block. Return final contract,
up/down quantities and diagnostic/gate evidence. Actual future prices must not
be an argument to planning or economic gating. Settlement A is primary; B is
a separately labelled sensitivity, never selected by realized cost.

Accepted API: `q3_api.simulate(..., decision_price=..., settlement_price=...,
q0_override=..., on_day_complete=...)`. Completion callback supplies
`(day, executed_initial_soc)` for Q4 trajectory-specific candidate cash scores.
Scores mature after two days, matching real Q2 V3.
The release hours are 0/6/12/18; template-left-endpoint slots at 06:00, 12:00,
18:00 have indexes 35/71/107. Confirm each future delivery slot at most once;
do not alter delivered slots. Official PV releases must be filtered by issue.

Q4 owns causal price forecasts and actual-delivery settlement. Its price API is
`q4_prices.forecast_prices(dates, actual_prices, prior_prices, day, issue_time)`
returning `PriceForecast(values, source_completed_at, model_id, issue_time)`.
Lag 7 is the frozen naive policy; days 0-6 use attachment 1 as declared prior.
Only fully completed price observations are available; no current-slot actual
price is inserted at a release. Each slot carries its own source timestamp.

Q4-2 reuses Q2 V3 candidate_grid, _recency_scenarios, two_stage_plan,
release_mature_scores, project_pending_energy and settle_causally. All 15
candidates are ranked using only matured dynamic actual-price cash scores.
Q4-3 must use the same Q2 midnight mechanism on its own carried SOC, then Q3
adjustments; Q2/Q4-2 executed SOC is not injected into Q4-3.

Provisional upstream: `runs/q2v3-r2-full-b0-a-20260913-01`. User explicitly
deferred the Q2 P2 RESET packaging issue and permits provisional progress.
Record actual hashes and unresolved review status; do not claim formal release.
Only Q4-2/Q4-3; no Q4-1. Portable Q2 is at
`solutions/Q3_Q4_JOINT/results/q2_provisional`. Implementation and bounded tests
only now. Annual runs and commit/push are on
hold. Later run Q3 once, then Q4 once, with one joint reviewer and no duplicate
annual reproduction.
