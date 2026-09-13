# Q4 V1 aligned implementation

Status: CONTENT_PASS_WITH_LIMITATIONS; score=91/100; formal_use=false.
Final review: `../../Q3_Q4_JOINT/others/round01_final_independent_review.md`.
The annual run completed once, after Q3. The implementation status JSON is a
historical P1 snapshot; current status is in root `VERSION_STATUS.json`.
The Q2 RESET export-validator issue was fixed during final delivery without a
model rerun. See `DELIVERY.md` for the final artifact paths. New-convention model
acceptance remains separate from delivery completeness.

Scope is Q4-2 and Q4-3 only. There is no Q4-1 task. Designated tables cover
2025-03-20, 2025-06-21, 2025-09-23 and 2025-12-21 after the annual execution.

## Commands (repository root)

```
.venv/bin/python -m pytest solutions/Q4_V1_ALIGNED/program/tests -q
.venv/bin/python solutions/Q4_V1_ALIGNED/program/run_q4.py --mode p1 --p1-days 3 --run-id q4-p1-20260913-01
.venv/bin/python solutions/Q4_V1_ALIGNED/program/run_q4.py --mode annual --run-id q4-v1-annual-20260913-01
```

The parent completed the authorized annual execution once, following Q3.
Existing run IDs are never overwritten; use a new ID for a new version.
One annual invocation includes Q4-2 and Q4-3 A primary/B sensitivity; these are
distinct policy trajectories, not duplicate reproduction. Nothing auto-commits.

## Mechanisms and interfaces

`q4_core.MidnightPolicy` directly calls the actual Q2 V3 15-candidate grid,
recency scenario generator (10 scenarios, 60-day window), two-stage optimizer,
28-day scoring window and two-day score maturity rule. It uses the pinned B0
forecast bundle and its own carried execution state; no archived pipeline or
Q2 realized grid/SOC is substituted for Q4 execution. Candidate scoring uses
actual prices only after the corresponding execution, then waits for maturity.

`q4_prices.forecast_prices` uses completed same-slot lag-7 prices, with attachment
1 prior for days 0-6. No current or future actual price is inserted at releases.
Cold-start prior timestamps are declared provenance, not observed labels.

`run_q4.q42` uses Q2's own projection and Battery A executor, no attachment 3.
`run_q4.q43` calls Q3 V3 `simulate` with forecast-price callback, separate actual
settlement array, causal midnight callback and completion callback for online
score history. Q4-3 uses official PV forecasts for release adjustments and
pending-slot projection. Q4-3 minus Q4-2 therefore measures the entire additional
information policy, not adjustment-only value or midnight-PV-only value.

Q4-3 needs `on_day_complete(day, executed_initial_soc)` in Q3 `simulate`.
No silent fallback or restricted name-only ONLINE-RISK-SP path is implemented.
The parent-provided portable Q2 package is preferred over ignored `runs/`.
Current core sources, committed source blobs, manifest and every upstream output
hash must match. Q3 sources and all Q4 inputs/outputs are included in run manifests.

## Delivery semantics

Each run writes `results/<id>` and `figures/<id>`. Main templates have exact names
`result4-2.xlsx` and `result4-3.xlsx`; B uses `result4-3-B-sensitivity.xlsx`.
The Q4-3 adjustment sheet holds final adjusted purchases and total ordinary cash
cost; up/down deltas and their fees are separate ledger columns. All filled
numeric cells, dates, labels, headers and row counts are read back.

Plan/storage tables follow template row blocks. Nominal 00:00/24:00 SOC fields
hold actual 00:10/next-day 00:10 states. Emergency events follow natural days:
Feb1 includes Jan31 plan slot143, Dec31 excludes Dec31 plan slot143. Full January
and cross-year bridge ledgers are retained. Annual summaries are plan-window
cash totals; emergency-template natural-window totals can differ at boundaries.

Settlement A charges base + 1.5*p*up + 0.5*p*down + 5*p*emergency. B changes
only the down fee sign, but its policy is independently executed on its own SOC.
No realized-cost selection between A and B. Terminal adjustment is reported as
cash + 0.4684*(6000-final_SOC), outside cash accounts. Battery A uses ideal
within-interval measurement feedback. Time B and one-slot-delay sensitivities
are not implemented here and must not be represented as completed evidence.

P1 runs three real January days; local tests additionally exercise day7/day8
price causality, actual March20 disjoint residual pools and accepted economic
gate branch, exact real Q2 planning equivalence, unfinished-midnight perturbation,
physical/cash tampering, natural-day bridge and template final quantities.
January P1 alone does not establish mature online adjustment performance.
