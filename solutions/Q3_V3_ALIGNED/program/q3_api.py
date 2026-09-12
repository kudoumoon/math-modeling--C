"""Causal Q3 mechanisms shared with Q4; no historical pipeline imports."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
from time import perf_counter
from typing import Callable

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.optimize import Bounds, LinearConstraint, milp

ROOT = Path(__file__).resolve().parents[3]
RUN_ID = "q2v3-r2-full-b0-a-20260913-01"
SOURCE_COMMIT = "17f25a508deaf7f9248ef18c3b498be12f5c083a"
MANIFEST_HASH = "d3b7453440b36ed32785ef5108a3b908634fa460472826ecfdf84d78f7463728"
BLOCKS = {6: (35, 71), 12: (71, 107), 18: (107, 144)}
DT = 1 / 6
EMIN, EMAX, LIMIT, ETA = 1200., 10800., 5000 / 6, .9
TERMINAL_VALUE = .4684


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite(value, shape=None, nonnegative=False):
    a = np.asarray(value, dtype=float)
    if (shape is not None and a.shape != shape) or not np.isfinite(a).all():
        raise ValueError(f"invalid finite array: {a.shape}, expected {shape}")
    if nonnegative and np.any(a < -1e-7):
        raise ValueError("negative input")
    return a


@dataclass
class Upstream:
    q0: np.ndarray
    load_forecast_kw: np.ndarray
    pv_forecast_kw: np.ndarray
    soc: np.ndarray
    daily: pd.DataFrame
    manifest: dict
    provenance: dict


def load_upstream(root=ROOT, run_path=None) -> Upstream:
    root = Path(root)
    portable = root / "solutions/Q3_Q4_JOINT/results/q2_provisional"
    run = Path(run_path) if run_path is not None else (portable if portable.exists() else root / "runs" / RUN_ID)
    if sha256(run / "manifest.json") != MANIFEST_HASH:
        raise ValueError("pinned Q2 manifest hash mismatch")
    m = json.loads((run / "manifest.json").read_text())
    if m["status"] != "complete" or m["git_commit"] != SOURCE_COMMIT:
        raise ValueError("Q2 run is not the authorized completed commit")
    cfg = m["configuration"]
    required = dict(forecast_arm="B0", time_mapping="A", battery_interpretation="A",
                    observation_delay_slots=0, compatibility_reset_on_report_start=False,
                    start_day=0, end_day=364)
    if any(cfg.get(k) != v for k, v in required.items()):
        raise ValueError("Q2 configuration differs from provisional authorization")
    checked = {}
    for section, base in (("input_hashes", root), ("outputs", run)):
        for name, expected in m[section].items():
            path = (base / name).resolve()
            if not path.is_relative_to(base.resolve()) or sha256(path) != expected:
                raise ValueError(f"Q2 {section} hash mismatch: {name}")
            checked[str(path.relative_to(root))] = expected
    # Validate the executed source at its commit, and expose later workspace edits.
    workspace_differences = []
    for name, expected in m["source_hashes"].items():
        blob = subprocess.run(["git", "show", f"{SOURCE_COMMIT}:{name}"], cwd=root,
                              check=True, capture_output=True).stdout
        if hashlib.sha256(blob).hexdigest() != expected:
            raise ValueError(f"Q2 committed source hash mismatch: {name}")
        if sha256(root / name) != expected:
            workspace_differences.append(name)
        checked[name + "@" + SOURCE_COMMIT] = expected
    with np.load(run / "policy_arrays.npz", allow_pickle=False) as f:
        q0 = _finite(f["G"], (365, 144), True).copy()
        soc = _finite(f["SOC"], (365, 145), True).copy()
    with np.load(run / "forecast_bundle.npz", allow_pickle=False) as f:
        load = _finite(f["load_b0"], (365, 144), True).copy()
        pv = _finite(f["pv_b0"], (365, 144), True).copy()
    ledger = pd.read_csv(run / "interval_ledger.csv")
    expected_dates = pd.date_range("2025-02-01", "2025-12-31")
    keys = pd.MultiIndex.from_product([expected_dates.strftime("%Y-%m-%d"), range(144)])
    actual_keys = pd.MultiIndex.from_frame(ledger[["plan_day", "time_index"]])
    if not keys.equals(actual_keys):
        raise ValueError("Q2 interval ledger has missing/reordered keys")
    if not np.allclose(ledger.planned_grid_kwh.to_numpy().reshape(-1, 144),
                       q0[31:], atol=1e-9, rtol=1e-12):
        raise ValueError("Q2 G and planned_grid_kwh differ")
    if not np.allclose(soc[:-1, -1], soc[1:, 0], atol=1e-7, rtol=0):
        raise ValueError("Q2 continuous SOC boundary mismatch")
    daily = pd.read_csv(run / "daily_ledger.csv")
    if daily.day_index.tolist() != list(range(365)):
        raise ValueError("Q2 daily ledger keys differ")
    q0.setflags(write=False)
    return Upstream(q0, load, pv, soc, daily, m, {
        "formal_use": False, "status": "PROVISIONAL_USER_AUTHORIZED",
        "upstream_version": RUN_ID, "source_commit": SOURCE_COMMIT,
        "manifest_sha256": MANIFEST_HASH, "validated_hashes": checked,
        "original_run": "runs/" + RUN_ID, "resolved_bundle": str(run),
        "workspace_source_differences": workspace_differences,
        "forecast_model_ids": [cfg["forecast_model_id"]],
        "p1_status": "NOT_ASSERTED", "p2_status": "PENDING",
        "time_mapping": "A", "battery_interpretation": "A",
        "residual_history_cutoff": "completed_at <= issue_time",
    })


@dataclass
class Inputs:
    dates: pd.DatetimeIndex
    load_kw: np.ndarray
    pv_kw: np.ndarray
    price: np.ndarray
    releases_kw: np.ndarray


def load_inputs(root=ROOT) -> Inputs:
    root = Path(root)
    manifest = json.loads((root / "data_manifest.json").read_text())
    needed = {"data/附件1.xlsx", "data/附件2.xlsx", "data/附件3.xlsx",
              "data/附件5/result3.xlsx"}
    entries = {x["path"]: x["sha256"] for x in manifest["files"]}
    for name in needed:
        if sha256(root / name) != entries[name]:
            raise ValueError(f"input hash mismatch: {name}")
    a1 = pd.read_excel(root / "data/附件1.xlsx")
    load = pd.read_excel(root / "data/附件2.xlsx", sheet_name=0)
    pv = pd.read_excel(root / "data/附件2.xlsx", sheet_name=1)
    dates = pd.DatetimeIndex(pd.to_datetime(load.iloc[:, 0]))
    if not dates.equals(pd.date_range("2025-01-01", periods=365)):
        raise ValueError("invalid daily dates")
    if not dates.equals(pd.DatetimeIndex(pd.to_datetime(pv.iloc[:, 0]))):
        raise ValueError("load/PV date mismatch")
    book = pd.read_excel(root / "data/附件3.xlsx")
    hours = book.iloc[:, 1].astype(str).str.extract(r"(\d+)")[0].astype(int)
    if not np.array_equal(hours, np.tile([0, 6, 12, 18], 365)):
        raise ValueError("invalid release hours")
    if not np.array_equal(pd.to_datetime(book.iloc[:, 0].ffill()), np.repeat(dates.values, 4)):
        raise ValueError("release date mismatch")
    return Inputs(dates, _finite(load.iloc[:, 1:], (365, 144), True),
                  _finite(pv.iloc[:, 1:], (365, 144), True),
                  _finite(a1.iloc[:, 1], (144,), True),
                  _finite(book.iloc[:, 2:], (1460, 24), True).reshape(365, 4, 24))


def feedback_step(soc, q, load_kwh, pv_kwh) -> dict:
    _finite([soc, q, load_kwh, pv_kwh], nonnegative=True)
    if not EMIN - 1e-6 <= soc <= EMAX + 1e-6:
        raise ValueError("SOC outside battery limits")
    surplus = q + pv_kwh - load_kwh
    c = min(max(surplus, 0.), LIMIT, max(0., (EMAX - soc) / ETA))
    d = min(max(-surplus, 0.), LIMIT, max(0., (soc - EMIN) * ETA))
    return dict(charge_kwh=c, discharge_kwh=d, emergency_kwh=max(-surplus - d, 0.),
                unused_supply_kwh=max(surplus - c, 0.), soc_after_kwh=soc + ETA*c - d/ETA)


def settle(q0, q, price, emergency, settlement="A") -> dict:
    if settlement not in ("A", "B"):
        raise ValueError("settlement must be A or B")
    q0, q, p, h = np.broadcast_arrays(q0, q, price, emergency)
    _finite([q0, q, p, h], nonnegative=True)
    u, r = np.maximum(q-q0, 0.), np.maximum(q0-q, 0.)
    base, up, down, ec = p*q0, 1.5*p*u, (.5 if settlement == "A" else -.5)*p*r, 5*p*h
    return dict(u_kwh=u, r_kwh=r, base_cost_yuan=base, up_cost_yuan=up,
                down_cost_yuan=down, ordinary_cost_yuan=base+up+down,
                emergency_cost_yuan=ec, total_cost_yuan=base+up+down+ec)


@dataclass
class ReleaseForecast:
    steps: np.ndarray
    load_kwh: np.ndarray
    pv_kwh: np.ndarray
    issue_time: pd.Timestamp
    anchor_slot: int | None
    anchor_day: int | None
    cutoff: pd.Timestamp | None
    load_correction_kwh: float

    @property
    def net_kwh(self):
        return self.load_kwh - self.pv_kwh


def build_release_forecast(inputs, upstream, day, hour, load_correction=True):
    if hour not in (0, 6, 12, 18):
        raise ValueError("invalid release hour")
    first = 0 if hour == 0 else hour*6-1
    steps = np.arange(first, 144)
    issue = inputs.dates[day] + pd.Timedelta(hours=hour)
    if hour:
        anchor_day, anchor_slot = day, hour*6-2
    elif day:
        anchor_day, anchor_slot = day-1, 142
    else:
        anchor_day, anchor_slot = None, None
    anchor = 0. if anchor_day is None else inputs.pv_kw[anchor_day, anchor_slot]
    cutoff = None if anchor_day is None else inputs.dates[anchor_day] + pd.Timedelta(minutes=(anchor_slot+2)*10)
    correction = 0.
    if hour and load_correction:
        completed = np.arange(max(0, first-12), first)
        correction = float(np.median((inputs.load_kw[day, completed] -
                                      upstream.load_forecast_kw[day, completed])*DT))
    load = np.maximum(0., upstream.load_forecast_kw[day, steps]*DT + correction)
    # Attachment 3 is the historical point-forecast interpolation model, with
    # its lead-zero proxy now taken strictly from the last completed interval.
    leads = (steps+1)*10 - hour*60
    nodes = np.r_[anchor, inputs.releases_kw[day, hour//6]]
    pv = np.interp(leads, np.arange(25)*60, nodes)*DT
    return ReleaseForecast(steps, load, pv, issue, anchor_slot, anchor_day, cutoff, correction)


def residual_pools(inputs, upstream, day, hour, risk_days=28, gate_days=14):
    """Disjoint historical release residuals; entire target horizon must mature."""
    issue = inputs.dates[day] + pd.Timedelta(hours=hour)
    candidates = [d for d in range(max(0, day-risk_days-gate_days-2), day)
                  if inputs.dates[d] + pd.Timedelta(days=1, minutes=10) <= issue]
    risk_ids = candidates[-risk_days:]
    gate_ids = candidates[max(0, len(candidates)-risk_days-gate_days):max(0, len(candidates)-risk_days)]
    width = 144 if hour == 0 else 145-hour*6
    def matrix(ids):
        rows = []
        for d in ids:
            f = build_release_forecast(inputs, upstream, d, hour)
            actual = (inputs.load_kw[d, f.steps]-inputs.pv_kw[d, f.steps])*DT
            rows.append(actual-f.net_kwh)
        return np.asarray(rows).reshape(-1, width)
    return matrix(risk_ids), matrix(gate_ids), risk_ids, gate_ids


def solve_adjustment(q0, net_kwh, price, start_soc, adjustable,
                     settlement="A", terminal_value=TERMINAL_VALUE):
    q0 = _finite(q0, nonnegative=True)
    n = len(q0)
    net = _finite(net_kwh, (n,))
    p = _finite(price, (n,), True)
    mask = np.asarray(adjustable, bool)
    if mask.shape != (n,) or settlement not in ("A", "B") or n == 0:
        raise ValueError("invalid adjustment contract")
    if not EMIN <= start_soc <= EMAX or terminal_value < 0:
        raise ValueError("invalid initial SOC or terminal value")
    # u,r,c,d,h,w,E,z. Binary z permits charging OR discharge/emergency.
    # Emergency energy can serve a deficit but cannot create stored inventory.
    oz = 7*n+1
    nv = oz+n
    obj = np.zeros(nv)
    obj[:n], obj[n:2*n] = 1.5*p, (.5 if settlement == "A" else -.5)*p
    obj[2*n:4*n], obj[4*n:5*n], obj[7*n] = 1e-7, 5*p, -terminal_value
    eq = sparse.lil_matrix((2*n, nv))
    for k in range(n):
        for offset, value in ((0,1), (n,-1), (2*n,-1), (3*n,1), (4*n,1), (5*n,-1)):
            eq[k, offset+k] = value
        eq[n+k, 6*n+k], eq[n+k, 6*n+k+1] = -1, 1
        eq[n+k, 2*n+k], eq[n+k, 3*n+k] = -ETA, 1/ETA
    bounds = [(0, None if m else 0) for m in mask]
    # With free spill and settlement A, reductions are weakly dominated.
    bounds += [(0, float(q0[k]) if mask[k] and settlement == "B" else 0) for k in range(n)]
    bounds += [(0, LIMIT)]*(2*n) + [(0, None)]*(2*n) + [(EMIN, EMAX)]*(n+1)
    bounds += [(0, 1)]*n
    bounds[6*n] = (start_soc, start_soc)
    started = perf_counter()
    rhs = np.r_[net-q0, np.zeros(n)]
    mode = sparse.lil_matrix((3*n, nv))
    upper = np.zeros(3*n)
    for k in range(n):
        mode[k,2*n+k],mode[k,oz+k] = 1,-LIMIT
        mode[n+k,3*n+k],mode[n+k,oz+k] = 1,LIMIT
        upper[n+k] = LIMIT
        emergency_limit = max(float(net[k]),0.)
        mode[2*n+k,4*n+k],mode[2*n+k,oz+k] = 1,emergency_limit
        upper[2*n+k] = emergency_limit
    integrality = np.r_[np.zeros(oz),np.ones(n)]
    result = milp(obj,integrality=integrality,
                  bounds=Bounds([b[0] for b in bounds],[np.inf if b[1] is None else b[1] for b in bounds]),
                  constraints=[LinearConstraint(eq.tocsr(),rhs,rhs),LinearConstraint(mode.tocsr(),-np.inf,upper)],
                  options={"time_limit": 30., "mip_rel_gap": 1e-8})
    if not result.success:
        raise RuntimeError(f"Q3 MILP failed ({result.status}): {result.message}")
    x = result.x
    residual = float(max(np.max(np.abs(eq.tocsr() @ x-rhs)),np.max(np.maximum(mode.tocsr() @ x-upper,0))))
    if residual > 1e-5:
        raise RuntimeError("MILP physical residual exceeds tolerance")
    return dict(q=np.maximum(q0+x[:n]-x[n:2*n], 0), u=x[:n], r=x[n:2*n],
                charge=x[2*n:3*n], discharge=x[3*n:4*n], soc=x[6*n:oz],
                emergency=x[4*n:5*n], max_residual=residual,
                solve_seconds=perf_counter()-started, objective=float(result.fun))


def gate_score(q0, q, net, price, start_soc, residuals, settlement="A"):
    """Actual feedback rollout on held-out residual paths, fees counted once."""
    if len(residuals) == 0:
        raise ValueError("gate requires held-out historical residuals")
    fee = float(np.sum(settle(q0, q, price, np.zeros(len(q)), settlement)["ordinary_cost_yuan"]))
    scores = []
    for residual in residuals:
        soc, ec = start_soc, 0.
        for k, value in enumerate(net+residual):
            a = feedback_step(soc, q[k], max(value, 0), max(-value, 0))
            soc = a["soc_after_kwh"]
            ec += 5*price[k]*a["emergency_kwh"]
        scores.append(fee+ec-TERMINAL_VALUE*soc)
    return float(np.mean(scores))


def simulate(inputs, upstream, *, start_day=0, end_day=364, adjustment_start_day=31,
             settlement="A", release_hours=(6, 12, 18), decision_price=None,
             settlement_price=None, q0_override: Callable | None = None,
             observation_delay_slots=0, on_day_complete: Callable | None = None):
    """One continuous causal replay. Callback q0 is frozen BEFORE bridge truth."""
    if not 0 <= start_day <= end_day < len(inputs.dates):
        raise ValueError("invalid replay window")
    if observation_delay_slots != 0 or not set(release_hours) <= BLOCKS.keys():
        raise ValueError("invalid observation delay or release schedule")
    prices = np.broadcast_to(inputs.price, inputs.load_kw.shape) if settlement_price is None else _finite(settlement_price, inputs.load_kw.shape, True)
    price_at = decision_price or (lambda day, hour, steps: inputs.price[steps])
    rows, decisions, plans = [], [], []
    # A sliced test resumes the authorized upstream midnight state, not E144.
    soc = 6000. if start_day == 0 else float(upstream.soc[start_day-1, 143])
    pending = None
    if start_day:
        d = start_day-1
        pending = dict(day=d, q0=upstream.q0[d].copy(), q=upstream.q0[d].copy(),
                       forecast=build_release_forecast(inputs, upstream, d, 18),
                       counts=np.zeros(144, int), source=np.full(144, "Q2", object))
    previous_net = 0. if start_day == 0 else float((inputs.load_kw[start_day-1,142]-inputs.pv_kw[start_day-1,142])*DT)

    def execute(record, step):
        nonlocal soc, previous_net
        d = record["day"]
        load, pv = inputs.load_kw[d,step]*DT, inputs.pv_kw[d,step]*DT
        q = record["q"][step]
        before = soc
        if observation_delay_slots == 0:
            a = feedback_step(soc, q, load, pv)
        else:
            command = feedback_step(soc, q, max(previous_net, 0), max(-previous_net, 0))
            c, dis = command["charge_kwh"], command["discharge_kwh"]
            balance = q+pv+dis-load-c
            a = dict(charge_kwh=c, discharge_kwh=dis, emergency_kwh=max(-balance,0),
                     unused_supply_kwh=max(balance,0), soc_after_kwh=soc+ETA*c-dis/ETA)
        previous_net, soc = load-pv, a["soc_after_kwh"]
        cash = {k: float(v) for k,v in settle(record["q0"][step], q, prices[d,step], a["emergency_kwh"], settlement).items()}
        start = inputs.dates[d]+pd.Timedelta(minutes=(step+1)*10)
        rows.append(dict(plan_day=inputs.dates[d], day_index=d, time_index=step,
                         interval_start=start, interval_end=start+pd.Timedelta(minutes=10),
                         natural_day=start.normalize(), q0_kwh=record["q0"][step],
                         planned_grid_kwh=record["q0"][step], qfinal_kwh=q,
                         price_yuan_per_kwh=prices[d,step], load_actual_kwh=load,
                         pv_actual_kwh=pv, soc_before_kwh=before,
                         confirmation_count=int(record["counts"][step]),
                         release_used=str(record["source"][step]), settlement=settlement,
                         observation_delay_slots=observation_delay_slots, **a, **cash))
        if step == 143 and on_day_complete is not None and d >= start_day:
            on_day_complete(d, record["actual_initial_soc"])

    for day in range(start_day, end_day+1):
        issue0 = inputs.dates[day]
        # Estimate the uncompleted prior-day bridge using the prior release.
        if pending is None:
            predicted_initial = soc
        else:
            f = pending["forecast"]
            projected = feedback_step(soc, pending["q"][143], f.load_kwh[-1], f.pv_kwh[-1])
            predicted_initial = projected["soc_after_kwh"]
        q0 = (upstream.q0[day].copy() if q0_override is None else
              _finite(q0_override(day, predicted_initial), (144,), True).copy())
        f0 = build_release_forecast(inputs, upstream, day, 0)
        record = dict(day=day, q0=q0, q=q0.copy(), forecast=f0,
                      counts=np.zeros(144, int), source=np.full(144, "0", object))
        if pending is not None:
            execute(pending, 143)
        actual_initial = soc
        record["actual_initial_soc"] = actual_initial
        plan = dict(day_index=day, plan_day=issue0, issue_time=issue0,
                    planned_initial_energy_kwh=predicted_initial,
                    executed_initial_energy_kwh=actual_initial,
                    upstream_planned_initial_energy_kwh=float(upstream.daily.iloc[day].planned_initial_energy_kwh),
                    planned_initial_source="previous_confirmed_contract_and_last_release",
                    q0_source="Q2_G_direct" if q0_override is None else "Q4_causal_callback")
        for step in range(143):
            hour = next((h for h,(first,_) in BLOCKS.items() if first == step), None)
            if hour is not None:
                f = build_release_forecast(inputs, upstream, day, hour)
                record["forecast"] = f
                if day >= adjustment_start_day and hour in release_hours:
                    first, end = BLOCKS[hour]
                    risk, gate, risk_ids, gate_ids = residual_pools(inputs, upstream, day, hour)
                    margin = np.maximum(0, np.quantile(risk, .65, axis=0)) if len(risk)>=7 else np.zeros(len(f.steps))
                    p = _finite(price_at(day, hour, f.steps.copy()), (len(f.steps),), True)
                    baseline = record["q"][f.steps].copy()
                    candidate = solve_adjustment(baseline, f.net_kwh+margin, p, soc,
                                                 f.steps < end, settlement)
                    keep_score = new_score = None
                    accepted = False
                    if len(gate) >= 7:
                        keep_score = gate_score(baseline, baseline, f.net_kwh, p, soc, gate, settlement)
                        new_score = gate_score(baseline, candidate["q"], f.net_kwh, p, soc, gate, settlement)
                        accepted = new_score < keep_score-1e-6
                    if accepted:
                        record["q"][first:end] = candidate["q"][:end-first]
                    record["counts"][first:end] += 1
                    record["source"][first:end] = str(hour)
                    decisions.append(dict(day_index=day, plan_day=issue0, issue_time=f.issue_time,
                                          release_hour=hour, anchor_day=f.anchor_day, anchor_slot=f.anchor_slot,
                                          history_cutoff=f.cutoff, residual_history_cutoff=f.issue_time,
                                          risk_days=json.dumps(risk_ids), gate_days=json.dumps(gate_ids),
                                          first_slot=first, end_slot_exclusive=end, soc_at_issue_kwh=soc,
                                          keep_score=keep_score, new_score=new_score, accepted=accepted,
                                          reason="heldout_improvement" if accepted else "keep_no_improvement_or_insufficient_history",
                                          solve_seconds=candidate["solve_seconds"], max_residual=candidate["max_residual"],
                                          load_correction_kwh=f.load_correction_kwh, settlement=settlement))
            execute(record, step)
        pending = record
        plans.append(plan)
    execute(pending, 143)
    return pd.DataFrame(rows), pd.DataFrame(decisions), pd.DataFrame(plans)
