# Q4 source freeze handoff

Date: 2026-09-13. Implementation is frozen for parent source commit.
No remaining local implementation blocker was identified by the completed
bounded checks. This is not an independent review or formal release.

Final read-only verification against `results/q4-p1-20260913-01/manifest.json`:

- No changed or newly added source paths in the captured Q4/Q3/Q2 source set.
- No output hash mismatches.
- All six Q4 attachment/template hashes match the frozen data manifest.
- Portable Q2 provisional run and its source/input/output hashes verified.
- Eight local tests passed; three real days completed for Q4-2 and Q4-3 A/B.
- All three interval ledgers and workbook readbacks passed.

P1 manifest SHA-256:
`e3ccc0a3c47c65ebc47d87bb5944ecdd0f994bc97406d0f5ce1cd47957890b4e`.
The manifest contains the per-file source hashes; use those as the freeze set.
No further source edits or runs are planned by this worker.

Remaining release prerequisites and disclosed limitations:

- Parent source commit, Q3 annual execution, then Q4 annual execution remain
  outstanding. No annual execution was started by this worker.
- Q4 P1 already exists; any further P1 is a bounded parent-directed check,
  not a prerequisite to duplicate annual reproduction.
- Annual monthly/designated-date tables and economic evidence are pending.
- Joint independent review and scores have not been issued for Q4.
- Q2 P2 RESET packaging remains explicitly deferred; `formal_use=false`.
- Time B and one-slot-delay sensitivities are not implemented. A/B settlement
  policies are implemented, but their annual evidence is pending.
- Q4-3 versus Q4-2 measures the whole additional-information policy, including
  official-PV pending-slot projection, not adjustment-only causal attribution.

Parent annual command, prepared but not executed:

```
.venv/bin/python solutions/Q4_V1_ALIGNED/program/run_q4.py --mode annual --run-id q4-v1-annual-20260913-01
```

For an explicitly requested additional bounded P1, use a fresh run ID:

```
.venv/bin/python solutions/Q4_V1_ALIGNED/program/run_q4.py --mode p1 --p1-days 3 --run-id q4-p1-postcommit-20260913-01
```
