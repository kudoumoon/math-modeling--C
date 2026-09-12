# Q3 V3 / Q4 reusable interface

Status: implemented, bounded local P1 passed; PROVISIONAL, no P2 release implied.
User authorizes only Q2 run `q2v3-r2-full-b0-a-20260913-01` at
`17f25a508deaf7f9248ef18c3b498be12f5c083a` as provisional upstream.
Q2 finalizer RESET comparison remains parked. Parent owns joint reports and
root VERSION_STATUS. No annual reproduction or git publication in this task.

Import `q3_api` with this version's `program` directory on sys.path.
Stable public functions (keyword arguments recommended):

- `load_upstream(root=ROOT, run_path=None) -> Upstream`: verifies pinned
  manifest, commit source blobs, inputs, output hashes and G/ledger equality.
  Default is the parent's portable `solutions/Q3_Q4_JOINT/results/q2_provisional`
  bundle when present, otherwise the original run. The original run identity
  remains pinned. Current upstream workspace differences are disclosed.
- `load_inputs(root=ROOT) -> Inputs`: dates, actual load/PV in kW, fixed
  prices, attachment 3 values shaped (days, 4, 24).
- `build_release_forecast(inputs, upstream, day, hour, load_correction=True)
  -> ReleaseForecast`: steps, load_kwh, pv_kwh, net_kwh, issue_time,
  anchor_slot and cutoff. No future actuals or future releases.
- `solve_adjustment(q0, net_kwh, price, start_soc, adjustable,
  settlement='A', terminal_value=0.4684) -> dict`: all input vectors describe
  the remaining horizon, adjustable is a boolean mask. Returns q, u, r,
  planned battery states and solver diagnostics. Price is a decision forecast.
  Uses MILP binary charging mode: c*d=0 and c*h=0. Emergency energy cannot
  charge the battery. Settlement A disables weakly dominated reductions.
- `feedback_step(soc, q, load_kwh, pv_kwh) -> dict`: physical Battery A.
- `settle(q0, q, price, emergency, settlement='A') -> dict`: array-valued
  base, up, down and emergency cash components. Price is actual delivery price.
- `simulate(inputs, upstream, *, start_day=0, end_day=364,
  adjustment_start_day=31, settlement='A', release_hours=(6,12,18),
  decision_price=None, settlement_price=None, q0_override=None,
  observation_delay_slots=0, on_day_complete=None)
  -> (interval_ledger, decisions, daily_plans)`.
  Q4 supplies `decision_price(day, hour, steps)` using only its own causal
  price information; `settlement_price` is (days,144). `q0_override` is a
  callback `(day, predicted_initial_soc) -> 144-vector`, invoked at midnight
  before the preceding bridge truth is consumed. Q3 default uses G directly.
  `on_day_complete(day, executed_initial_soc)` runs exactly once after slot143
  executes; the next midnight plan was already issued before that callback.
  OBS1 is rejected, not presented as a validated sensitivity.

Mapping A: 06:00 last completed slot is 34; pending starts at 35, with
non-overlapping editable blocks [35,71), [71,107), [107,144).
At midnight anchor is previous day slot142, never slot143. January 1 has
no preceding observation; use declared zero PV prior. Next-day q0 is frozen
before executing prior-day slot143 (00:00-00:10). Actual SOC stays continuous.
Settlement A is primary (down fee +0.5*p*r); B (-0.5*p*r) is sensitivity.
The q0 base is charged once, adjustments once per slot, emergencies at 5*p.
No archive modules are imported. Full-run results remain provisional.

CLI from repository root:
` .venv/bin/python solutions/Q3_V3_ALIGNED/program/run_q3_v3.py --run-id q3v3-r1 `

Completed local diagnostic: `--run-id q3v3-p1 --p1`, March 20-22, 2025.
Ten targeted tests pass; A and B each accepted 6 and rejected 3 releases.
The P1 manifest records live source hashes, current Git HEAD and dirty status.
Parent may commit these exact sources before annual execution. No duplicate
P1 is necessary unless sources change; annual CLI verifies the bound hashes.

Results: `results/<run-id>/<baseline|A|B|A_6|A_6_12>/` (P1 uses first three).
Each contains full execution `interval_ledger.csv`, `decisions.csv`,
`daily_plans.csv`, report-window daily/monthly tables, designated dates
03-20/06-21/09-23/12-21, sample months 03/06/09/12, `result3.xlsx`,
and full populated-cell template readback. Figures live under `figures/<run-id>`.
Annual replay begins January 1 at 6000 kWh and adjustments begin February 1.
Natural-day emergency output includes Jan31 slot143 and excludes Dec31 slot143;
the complete ledger retains both. Four-hour template grouping and nominal
boundary fields follow Time A, with exact natural-day blocks exported separately.

Scope limitation: q0 is Q2 G, so this evaluates only the incremental 6/12/18
release adjustment mechanism, not the value of optimizing q0 with midnight
official PV forecasts. January is a common unadjusted warmup. Parameters are
fixed ex ante (28 risk days, 14 disjoint gate days, 0.65 positive residual
quantile, at least 7 samples per pool); no July-December result selects them.
The current controller uses ideal immediate Battery A measurements. Time B
and delayed measurements are not evaluated in this restricted provisional run.
