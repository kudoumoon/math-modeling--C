"""Nine Q2 delivery figures from frozen tables. No model imports or optimization.

Default input: results/final_v1. --from-figure-data redraws the portable bundle.
--profile-run only profiles the existing main run while the finalizer is pending.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
os.environ.setdefault("MPLCONFIGDIR", "/tmp/q2-delivery-figure-mpl")
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import numpy as np
import pandas as pd
from PIL import Image

from figure_tools.setup_style import setup_style
from figure_tools.export_figure import export_figure
from figure_tools.visual_qa import audit_layout, render_preview
from figure_tools.check_figure import check_figure
from figure_tools.profile_data import profile_data

ROOT = Path(__file__).resolve().parents[3]
VERSION = Path(__file__).resolve().parents[1]
PROGRAM = Path(__file__).resolve().parent
DATA = VERSION / "results/figure_data"
FIGURES = VERSION / "figures/delivery_r1"
OTHERS = VERSION / "others"
MAIN_RUN = VERSION / "results/annual_runs/q2v3-r2-full-b0-a-20260913-01"
CASES = ["main", "battery_b", "time_b", "delay_1", "reset_feb"]
CASE_LABELS = ["Main B0 (reference)", "Battery B", "Time B (legacy)", "One-slot delay", "February SOC reset"]
COLORS = {"load": "#0072B2", "pv": "#D55E00", "cash": "#0072B2", "emergency": "#D55E00"}
TOL = 1e-7
PLAN_SCOPE = "Primary B0 | old Time A plan dates | Feb 1-Dec 31, 2025 (334 days)"
RAW_SCOPE = "Q2 primary B0 | Attachment 2 observations | old Time A rows | 365 days, 2025"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_default(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (pd.Timestamp, Path)):
        return str(value)
    raise TypeError(type(value).__name__)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, default=json_default) + "\n", encoding="utf-8")


def snapshot(paths, base=ROOT):
    return {str(path.relative_to(base)): sha256(path) for path in sorted(set(paths))}


def source_snapshot():
    return snapshot([Path(__file__), *sorted(p for p in (PROGRAM / "figure_tools").glob("*") if p.is_file())])


def assert_close(actual, expected, label):
    if not np.allclose(actual, expected, atol=1e-5, rtol=1e-12):
        raise ValueError(f"inconsistent delivery tables: {label}")


def raw_tables():
    load = pd.read_excel(ROOT / "data/附件2.xlsx", sheet_name=0)
    pv = pd.read_excel(ROOT / "data/附件2.xlsx", sheet_name=1)
    price = pd.read_excel(ROOT / "data/附件1.xlsx").iloc[:, 1].to_numpy(float)
    dates = pd.DatetimeIndex(pd.to_datetime(load.iloc[:, 0]))
    if not dates.equals(pd.date_range("2025-01-01", periods=365)) or not dates.equals(pd.DatetimeIndex(pd.to_datetime(pv.iloc[:, 0]))):
        raise ValueError("attachment date identities differ")
    arrays = {"load": load.iloc[:, 1:].to_numpy(float), "pv": pv.iloc[:, 1:].to_numpy(float)}
    if any(a.shape != (365,144) or not np.isfinite(a).all() or (a < 0).any() for a in arrays.values()):
        raise ValueError("invalid attachment observation array")
    daily = pd.DataFrame({"date": dates, "quarter": dates.quarter,
        "load_mwh": arrays["load"].sum(axis=1)/6000., "pv_mwh": arrays["pv"].sum(axis=1)/6000.})
    observations = pd.DataFrame({"plan_day": np.repeat(dates,144), "time_index": np.tile(np.arange(144),365),
        "load_actual_kw": arrays["load"].ravel(), "pv_actual_kw": arrays["pv"].ravel()})
    profile = []
    for name, values in arrays.items():
        q10, median, q90 = np.quantile(values, [.1,.5,.9], axis=0)
        profile.append(pd.DataFrame({"variable": name, "time_index": np.arange(144),
            "nominal_hour": np.arange(144)/6, "median_kw": median, "p10_kw": q10,
            "p90_kw": q90, "price_yuan_per_kwh": price}))
    return {"raw_daily": daily, "raw_diurnal": pd.concat(profile, ignore_index=True), "raw_observations": observations}


def normalize_main(daily, interval):
    daily = daily.loc[daily.day_index.between(31,364)].copy().sort_values("day_index")
    daily["date"] = pd.to_datetime(daily.date)
    interval = interval.copy().sort_values(["plan_day", "time_index"])
    interval["plan_day"] = pd.to_datetime(interval.plan_day)
    interval["interval_start"] = pd.to_datetime(interval.interval_start)
    interval["interval_end"] = pd.to_datetime(interval.interval_end)
    expected = pd.date_range("2025-02-01", "2025-12-31")
    if not pd.DatetimeIndex(daily.date).equals(expected) or len(interval) != 334*144:
        raise ValueError("main delivery requires 334 complete February-December planning days")
    if set(interval.forecast_arm) != {"B0"} or set(interval.forecast_model_id) != {"Q2V2-SW2-REC5"}:
        raise ValueError("the delivered primary must be frozen B0")
    expected_keys = pd.MultiIndex.from_product([expected, range(144)])
    if not expected_keys.equals(pd.MultiIndex.from_frame(interval[["plan_day", "time_index"]])):
        raise ValueError("missing, duplicated or reordered interval keys")
    starts = interval.plan_day + pd.to_timedelta((interval.time_index+1)*10, unit="min")
    if not (interval.interval_start == starts).all():
        raise ValueError("expected old Time A: slot0 starts at 00:10, slot143 at next midnight")
    numeric = interval.select_dtypes(include="number")
    if not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("nonfinite interval observations")
    if not np.array_equal(daily.latest_full_score_day_released, daily.day_index-2):
        raise ValueError("candidate history maturity differs from frozen policy")
    daily["month"] = daily.date.dt.strftime("%Y-%m")
    interval["month"] = interval.plan_day.dt.strftime("%Y-%m")
    interval["total_cost_yuan"] = interval.plan_cost_yuan + interval.emergency_cost_yuan
    sums = interval.groupby("plan_day").total_cost_yuan.sum()
    assert_close(sums.to_numpy(), daily.realized_total_cost_yuan.to_numpy(), "daily cash")
    return daily, interval


def candidate_tables(daily):
    histories = [json.loads(value) for value in daily.candidate_scores_completed_before_issue]
    keys = list(histories[0])
    if len(keys) != 15 or any(set(row) != set(keys) for row in histories):
        raise ValueError("candidate log must contain the same 15 identities")
    rows = []
    for index, key in enumerate(keys, 1):
        match = re.fullmatch(r"(nocvar|cvar_t([\d.]+)_r([\d.]+))_g([\d.]+)", key)
        if match is None:
            raise ValueError(f"unknown frozen candidate identity: {key}")
        beta, rho = (None, 0.) if match[1] == "nocvar" else (float(match[2]),float(match[3]))
        gamma = float(match[4])
        compact = f"N | {gamma:.2f}" if beta is None else f"{100*beta:.0f}/{100*rho:02.0f} | {gamma:.2f}"
        rows.append(dict(candidate_id=key, candidate_index=index, beta=beta, rho=rho,
            gamma=gamma, label=compact, selected_days=int((daily.selected_candidate == key).sum())))
    key_table = pd.DataFrame(rows)
    lookup = key_table.set_index("candidate_id")
    trace = daily[["date", "day_index", "selected_candidate", "latest_full_score_day_released"]].copy()
    trace["candidate_index"] = trace.selected_candidate.map(lookup.candidate_index)
    trace["gamma"] = trace.selected_candidate.map(lookup.gamma)
    if trace.candidate_index.isna().any():
        raise ValueError("selected candidate absent from the recorded candidate set")
    return key_table, trace


def derive_tables(tables):
    daily, interval = tables["main_daily"], tables["main_interval"]
    keys, trace = candidate_tables(daily)
    soc = interval.pivot(index="plan_day", columns="time_index", values="actual_soc_before_kwh")
    soc.columns = [f"slot_{i:03d}" for i in range(144)]
    soc = soc.reset_index()
    hourly = interval.assign(nominal_hour=interval.time_index//6).groupby("nominal_hour", as_index=False).agg(
        emergency_kwh=("emergency_kwh", "sum"), active_intervals=("emergency_kwh", lambda s: int((s>TOL).sum())),
        intervals=("time_index", "size"))
    values = np.sort(daily.emergency_kwh.to_numpy())
    ecdf = pd.DataFrame({"daily_emergency_kwh": values, "cumulative_fraction": np.arange(1,len(values)+1)/len(values)})
    risk = []
    for month, frame in daily.groupby("month"):
        q1, median, q3, p95 = np.quantile(frame.realized_total_cost_yuan, [.25,.5,.75,.95])
        risk.append(dict(month=month, days=len(frame), q25_cash_yuan=q1, median_cash_yuan=median,
            q75_cash_yuan=q3, p95_cash_yuan=p95, max_cash_yuan=float(frame.realized_total_cost_yuan.max()),
            emergency_days=int((frame.emergency_kwh>TOL).sum()),
            emergency_day_fraction=float((frame.emergency_kwh>TOL).mean())))
    tables.update(candidate_key=keys, candidate_trace=trace, soc_plan_grid=soc,
        emergency_by_hour=hourly, emergency_ecdf=ecdf, monthly_risk=pd.DataFrame(risk))
    return tables


def load_final(source):
    filenames = {"main_daily": "q2_daily_ledger.csv", "main_interval": "q2_interval_ledger.csv",
        "monthly_summary": "q2_monthly_summary.csv", "sensitivity_summary": "q2_sensitivity_summary.csv"}
    missing = [str(source/name) for name in filenames.values() if not (source/name).is_file()]
    if missing:
        raise FileNotFoundError("Finalizer tables are not ready; no figure result was fabricated: " + ", ".join(missing))
    inputs = [source/name for name in filenames.values()]
    tables = {name: pd.read_csv(source/filename) for name, filename in filenames.items()}
    tables["main_daily"], tables["main_interval"] = normalize_main(tables["main_daily"],tables["main_interval"])
    monthly = tables["monthly_summary"].sort_values("month")
    grouped = tables["main_interval"].groupby("month")
    if monthly.month.tolist() != sorted(tables["main_daily"].month.unique()):
        raise ValueError("monthly summary window differs from the main ledger")
    for field in ("plan_cost_yuan", "emergency_cost_yuan", "total_cost_yuan", "emergency_kwh"):
        assert_close(monthly[field], grouped[field].sum().to_numpy(), field)
    tables["monthly_summary"] = monthly.reset_index(drop=True)
    sensitivity = tables["sensitivity_summary"].set_index("case")
    if set(sensitivity.index) != set(CASES) or sensitivity.index.has_duplicates:
        raise ValueError("sensitivity must contain the five frozen cases")
    for case in CASES:
        if case == "main":
            complete = tables["main_daily"]
        else:
            path = source / f"q2_{case}_daily_ledger_all.csv"
            if not path.is_file():
                raise FileNotFoundError(f"333-day sensitivity verification needs finalizer table {path.name}")
            inputs.append(path)
            complete = pd.read_csv(path)
        common = complete.loc[complete.day_index.between(31,363)].sort_values("day_index")
        if common.day_index.tolist() != list(range(31,364)):
            raise ValueError(f"{case}: common sensitivity window is not exactly 333 plan dates")
        for output, value in (("common_333d_total_cost_yuan", common.realized_total_cost_yuan.sum()),
                              ("common_333d_emergency_kwh", common.emergency_kwh.sum())):
            assert_close(sensitivity.loc[case,output], value, case+" "+output)
    tables["sensitivity_summary"] = sensitivity.loc[CASES].reset_index()
    for name in ("q2_release_manifest.json", "q2_main_config.json", "q2_main_source_manifest.json"):
        if (source/name).is_file():
            inputs.append(source/name)
    tables.update(raw_tables())
    inputs += [ROOT/"data/附件1.xlsx", ROOT/"data/附件2.xlsx"]
    return derive_tables(tables), inputs


def profile_inputs(tables):
    targets = {"raw_observations": [], "raw_daily": ["quarter"],
        "main_daily": ["month"], "main_interval": ["month"]}
    return {name: profile_data(tables[name].drop(columns=["candidate_scores_completed_before_issue"],errors="ignore"), groups)
            for name, groups in targets.items()}


def save_tables(tables, inputs):
    DATA.mkdir(parents=True, exist_ok=True)
    mapping = {}
    compressed = {"raw_observations", "main_daily", "main_interval", "soc_plan_grid"}
    for name, table in tables.items():
        filename = name + (".csv.gz" if name in compressed else ".csv")
        table.to_csv(DATA/filename, index=False, compression="infer")
        mapping[name] = filename
    manifest = dict(status="complete", tables=mapping, source_input_hashes=snapshot(inputs),
        data_hashes={filename: sha256(DATA/filename) for filename in mapping.values()},
        policy="frozen B0", time_mapping="old Time A planning rows, not a natural-day projection",
        report_days=334, sensitivity_days=333, raw_days=365,
        portable_redraw="python program/q2_delivery_figures.py --from-figure-data")
    write_json(DATA/"figure_source_manifest.json", manifest)
    return manifest


def load_portable():
    manifest = json.loads((DATA/"figure_source_manifest.json").read_text())
    for filename, digest in manifest["data_hashes"].items():
        if sha256(DATA/filename) != digest:
            raise ValueError(f"figure source changed: {filename}")
    tables = {name: pd.read_csv(DATA/filename) for name,filename in manifest["tables"].items()}
    tables["main_daily"], tables["main_interval"] = normalize_main(tables["main_daily"], tables["main_interval"])
    for key, column in (("raw_daily","date"),("candidate_trace","date"),("soc_plan_grid","plan_day")):
        tables[key][column] = pd.to_datetime(tables[key][column])
    return tables, manifest


def canvas(title, subtitle, *, height=4.5, rows=1, cols=1, ratios=None, sharey=False, left=.105):
    fig, axes = plt.subplots(rows, cols, figsize=(7.2,height), squeeze=False,
        sharey=sharey, gridspec_kw={"width_ratios": ratios} if ratios else None)
    fig.subplots_adjust(left=left, right=.97, bottom=.23, top=.82, wspace=.30, hspace=.62)
    fig.text(left,.965,title,fontsize=11,fontweight="bold",va="top")
    fig.text(left,.905,subtitle,fontsize=7.5,va="top")
    for axis in axes.ravel():
        axis.grid(axis="y",alpha=.2,linewidth=.5)
        axis.set_axisbelow(True)
    return fig, axes.ravel()


def footer(fig, text, left=.105):
    note=fig.text(left,.035,text,fontsize=7,va="bottom",linespacing=1.5)
    note.set_gid("q2_figure_footer")


def audit_footer_spacing(fig):
    """The skill audit checks clipping/ticks, but not footer versus axis labels."""
    fig.canvas.draw()
    renderer=fig.canvas.get_renderer()
    note=next(text for text in fig.texts if text.get_gid()=="q2_figure_footer")
    footer_box=note.get_window_extent(renderer)
    gaps=[]
    for axis in fig.axes:
        for label in [axis.xaxis.label,*axis.get_xticklabels()]:
            if not label.get_visible() or not label.get_text().strip():
                continue
            box=label.get_window_extent(renderer)
            if box.x0 < footer_box.x1 and box.x1 > footer_box.x0:
                gap=(box.y0-footer_box.y1)*72/fig.dpi
                gaps.append(gap)
                if gap < 4.:
                    raise RuntimeError(f"footer and x-axis label need separation: {label.get_text()!r}, {gap:.2f} pt")
    return {"passed":True,"minimum_gap_points":min(gaps),"required_gap_points":4.}


def month_ticks(axis):
    axis.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[2,4,6,8,10,12]))
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%b"))


def raw_distribution(t):
    fig, axes = canvas("Observed daily load and PV energy", RAW_SCOPE, cols=2)
    daily = t["raw_daily"]
    bins = np.linspace(0, np.ceil(daily[["load_mwh","pv_mwh"]].to_numpy().max()/10)*10, 22)
    for axis, name in zip(axes,("load","pv")):
        values = daily[name+"_mwh"]
        axis.hist(values,bins=bins,color=COLORS[name],edgecolor="white",linewidth=.45)
        axis.axvline(values.median(),color="#222222",linestyle="--",linewidth=1,label=f"Median {values.median():.1f}")
        axis.set(xlabel=f"Daily {'PV' if name=='pv' else 'load'} energy (MWh)",ylabel="Observed days",xlim=(bins[0],bins[-1]))
        axis.legend(loc="upper left",frameon=False,fontsize=7)
    footer(fig,"365 observations per panel; identical bin edges. Energy = sum of 144 ten-minute powers / 6.\nAll days retained, including January warmup dates; no policy forecast is plotted.")
    return fig


def raw_diurnal(t):
    fig, axes = canvas("Daily demand, solar supply and the declared tariff", RAW_SCOPE,rows=2,height=5.4)
    for name, style in (("load","-"),("pv","--")):
        frame = t["raw_diurnal"].query("variable == @name")
        axes[0].plot(frame.nominal_hour,frame.median_kw/1000,color=COLORS[name],linestyle=style,label=name.upper()+" median")
        axes[0].fill_between(frame.nominal_hour,frame.p10_kw/1000,frame.p90_kw/1000,color=COLORS[name],alpha=.15)
    axes[0].set(ylabel="Observed power (MW)",xlim=(0,24),ylim=(0,None))
    axes[0].legend(loc="upper left",frameon=False,ncol=2,fontsize=7)
    frame=t["raw_diurnal"].query("variable == 'load'")
    axes[1].step(frame.nominal_hour,frame.price_yuan_per_kwh,where="post",color="#222222")
    axes[1].set(xlabel="Nominal Time A plan-row hour (slot / 6)",ylabel="Tariff (yuan/kWh)",xlim=(0,24),ylim=(0,None))
    for axis in axes:
        axis.set_xticks(np.arange(0,25,4))
    footer(fig,"Bands show the empirical 10th-90th percentiles across 365 days at each slot, not confidence intervals.\nAttachment 1 tariff is known; old Time A slot0 starts at 00:10 and slot143 at next-day 00:00.")
    return fig


def raw_relationship(t):
    fig, axes=canvas("Load and PV do not move together uniformly",RAW_SCOPE)
    daily=t["raw_daily"]
    for quarter,color,marker in zip(range(1,5),["#0072B2","#D55E00","#009E73","#333333"],["o","s","^","x"]):
        frame=daily[daily.quarter==quarter]
        axes[0].scatter(frame.pv_mwh,frame.load_mwh,s=16,color=color,marker=marker,alpha=.72,label=f"Q{quarter} (n={len(frame)})",linewidths=.5)
    axes[0].set(xlabel="Observed daily PV energy (MWh)",ylabel="Observed daily load energy (MWh)")
    axes[0].legend(loc="upper center",bbox_to_anchor=(.5,1.10),frameon=False,ncol=4,fontsize=7)
    r=daily[["load_mwh","pv_mwh"]].corr().iloc[0,1]
    footer(fig,f"All 365 paired observations; calendar quarters use both color and marker. Pearson r = {r:.3f}.\nDescriptive association only: no fitted model, causal claim, significance test or excluded outlier.")
    return fig


def process_soc(t):
    fig, axes=canvas("Executed battery state over the reporting window",PLAN_SCOPE,height=5.5)
    grid=t["soc_plan_grid"]
    axis=axes[0]
    mesh=axis.pcolormesh(np.arange(145)/6,np.arange(len(grid)+1),grid.iloc[:,1:].to_numpy()/1000,
        cmap="cividis",vmin=1.2,vmax=10.8,shading="flat",rasterized=False)
    dates=pd.to_datetime(grid.plan_day)
    positions=np.flatnonzero(dates.dt.day.to_numpy()==1)
    axis.set_yticks(positions+.5,dates.iloc[positions].dt.strftime("%b"))
    axis.set(xlabel="Nominal Time A plan-row hour (slot / 6)",ylabel="2025 plan date",xlim=(0,24),ylim=(len(grid),0))
    axis.set_xticks(np.arange(0,25,4))
    axis.grid(False)
    colorbar=fig.colorbar(mesh,ax=axis,pad=.02,aspect=30)
    colorbar.solids.set_rasterized(False)
    colorbar.set_label("Executed SOC before slot (MWh)")
    footer(fig,"All 48,096 recorded SOC-before states; fixed physical bounds 1.2-10.8 MWh. No smoothing.\nBattery A causal feedback; this shows executed states, not an economically optimal control claim.")
    return fig


def process_candidates(t):
    fig,axes=canvas("How the recorded online selector changes candidates",PLAN_SCOPE,cols=2,ratios=[4,1.4],sharey=True,height=5.7,left=.17)
    keys,trace=t["candidate_key"],t["candidate_trace"]
    for gamma,color,marker in ((0.,"#333333","o"),(.02,"#0072B2","s"),(.05,"#D55E00","^")):
        frame=trace[np.isclose(trace.gamma,gamma)]
        axes[0].scatter(frame.date,frame.candidate_index,s=11,color=color,marker=marker,linewidths=0,label=f"g={gamma:.2f}")
    axes[0].set_yticks(keys.candidate_index,keys.label,fontsize=7)
    axes[0].set(xlabel="2025 plan date",ylabel="beta / rho (%) | gamma",ylim=(15.8,.2))
    axes[0].legend(loc="upper center",bbox_to_anchor=(.5,1.11),ncol=3,frameon=False,fontsize=7)
    month_ticks(axes[0])
    axes[1].barh(keys.candidate_index,keys.selected_days,color="#777777",height=.66)
    axes[1].set(xlabel="Days selected",xlim=(0,keys.selected_days.max()*1.28))
    axes[1].grid(axis="x",alpha=.2)
    for row in keys.itertuples():
        axes[1].text(row.selected_days+1,row.candidate_index,str(row.selected_days),va="center",fontsize=7)
    footer(fig,"All 15 candidates retained, including zero selections; N denotes no CVaR. Gamma is scenario recency decay.\nRecorded selections use mature histories through d-2; counts are not evidence of candidate superiority.",left=.17)
    return fig


def process_emergency(t):
    fig,axes=canvas("When emergency purchases occur and how days differ",PLAN_SCOPE,cols=2,height=4.7)
    hourly,ecdf=t["emergency_by_hour"],t["emergency_ecdf"]
    axes[0].bar(hourly.nominal_hour,hourly.emergency_kwh/1000,color=COLORS["emergency"],width=.82)
    axes[0].set(xlabel="Nominal plan-row hour",ylabel="Total emergency energy (MWh)",xlim=(-.7,23.7))
    axes[0].set_xticks([0,4,8,12,16,20,23])
    axes[1].step(np.r_[0,ecdf.daily_emergency_kwh/1000],np.r_[0,ecdf.cumulative_fraction],where="post",color="#222222")
    axes[1].set(xlabel="Daily emergency energy (MWh)",ylabel="Fraction of report days",ylim=(0,1.02),xlim=(0,None))
    axes[1].yaxis.set_major_formatter(PercentFormatter(1))
    active=int((t["main_daily"].emergency_kwh>TOL).sum())
    footer(fig,f"Hourly bars sum all 48,096 slots; the ECDF includes all 334 days, including {334-active} zero-emergency days.\nEmergency threshold for counts: 1e-7 kWh. This is observed feedback, not a forecast probability.")
    return fig


def result_cost(t):
    monthly=t["monthly_summary"]
    fig,axes=canvas("Monthly operating cash: scheduled and emergency",PLAN_SCOPE)
    x=np.arange(len(monthly))
    axes[0].bar(x,monthly.plan_cost_yuan/1e6,color=COLORS["cash"],label="Scheduled cash")
    axes[0].bar(x,monthly.emergency_cost_yuan/1e6,bottom=monthly.plan_cost_yuan/1e6,
        color=COLORS["emergency"],hatch="///",label="Emergency cash")
    axes[0].set_xticks(x,pd.to_datetime(monthly.month).dt.strftime("%b"))
    axes[0].set(xlabel="2025 plan month",ylabel="Total cash (million yuan)",ylim=(0,None))
    axes[0].legend(frameon=False,ncol=2,loc="upper center",bbox_to_anchor=(.5,1.12))
    total=float(monthly.total_cost_yuan.sum())
    footer(fig,f"Recorded 334-day total: {total:,.2f} yuan. Cash = scheduled purchases + five-times-tariff emergency purchases.\nMonthly totals are additive accounting quantities, with no inventory adjustment or claimed counterfactual saving.")
    return fig


def result_risk(t):
    daily,risk=t["main_daily"],t["monthly_risk"]
    fig,axes=canvas("Within-month cash tails and emergency-day frequency",PLAN_SCOPE,rows=2,height=5.8)
    months=risk.month.tolist()
    values=[daily.loc[daily.month==month,"realized_total_cost_yuan"].to_numpy()/1000 for month in months]
    axes[0].boxplot(values,positions=np.arange(len(months)),widths=.5,patch_artist=True,
        boxprops={"facecolor":"#DCEAF3","edgecolor":"#0072B2"},medianprops={"color":"#222222"},
        flierprops={"marker":"o","markersize":2,"markerfacecolor":"none","markeredgecolor":"#777777"})
    axes[0].scatter(np.arange(len(months)),risk.p95_cash_yuan/1000,marker="D",s=17,color=COLORS["emergency"],label="Empirical daily cash P95",zorder=3)
    axes[0].set(ylabel="Daily cash (1,000 yuan)",ylim=(0,None))
    axes[0].legend(frameon=False,fontsize=7,loc="upper center",bbox_to_anchor=(.5,1.21))
    axes[1].scatter(np.arange(len(months)),risk.emergency_day_fraction,color=COLORS["emergency"],s=25,marker="s")
    axes[1].vlines(np.arange(len(months)),0,risk.emergency_day_fraction,color=COLORS["emergency"],linewidth=1)
    axes[1].set(xlabel="2025 plan month (observed days)",ylabel="Days with emergency",ylim=(0,1))
    axes[1].yaxis.set_major_formatter(PercentFormatter(1))
    labels=[f"{pd.Timestamp(month).strftime('%b')}\n(n={n})" for month,n in zip(months,risk.days)]
    for axis in axes:
        axis.set_xticks(np.arange(len(months)),labels)
    footer(fig,"Boxes: median and IQR; whiskers: 1.5 IQR; outliers retained. P95 uses linear empirical interpolation.\n334 observed days, not independent replications; no confidence intervals, CVaR objective or significance claim.")
    return fig


def result_sensitivity(t):
    sensitivity=t["sensitivity_summary"].set_index("case").loc[CASES]
    fig,axes=canvas("Sensitivity on the same 333 planning dates", "All cases use frozen B0 | Feb 1-Dec 30, 2025 | Main A/A reference",cols=2,sharey=True,height=4.7,left=.245)
    for axis,field,scale,label in zip(axes,["common_333d_total_cost_yuan","common_333d_emergency_kwh"],
        [1e6,1000.],["Cash difference from main\n(million yuan)","Emergency difference from main\n(MWh)"]):
        differences=(sensitivity[field]-sensitivity.loc["main",field])/scale
        axis.axvline(0,color="#333333",linestyle="--",linewidth=.8)
        for y,value in enumerate(differences):
            axis.plot([0,value],[y,y],color="#777777",linewidth=1)
            axis.scatter(value,y,s=27,marker="D" if y==0 else "o",color="#222222" if y==0 else "#0072B2",zorder=3)
        axis.set(xlabel=label,ylim=(4.7,-.7))
        axis.margins(x=.2)
        axis.grid(axis="x",alpha=.2)
    axes[0].set_yticks(np.arange(5),CASE_LABELS,fontsize=7.5)
    footer(fig,"Each delta is recomputed from the finalizer's common_333d columns, verified against the frozen daily ledgers.\nTime B is the old right-endpoint sensitivity, not a new natural-day convention. No inventory adjustment.",left=.105)
    return fig


SPECS = [
    ("raw_q2_01_daily_energy", "raw", raw_distribution, ["raw_daily"], "Histogram", "Observed load and PV occupy different daily energy ranges."),
    ("raw_q2_02_diurnal_tariff", "raw", raw_diurnal, ["raw_diurnal"], "Line and empirical band", "Within-day load, PV and the known tariff have distinct temporal patterns."),
    ("raw_q2_03_load_pv_relation", "raw", raw_relationship, ["raw_daily"], "Scatter", "Daily PV is not a sufficient description of daily load variation."),
    ("process_q2_01_executed_soc", "process", process_soc, ["soc_plan_grid"], "Heatmap", "The stored executed SOC shows daily and seasonal battery-state variation within physical bounds."),
    ("process_q2_02_candidate_selection", "process", process_candidates, ["candidate_key","candidate_trace"], "Categorical trace and count bars", "The recorded selector uses multiple candidates with uneven selection counts."),
    ("process_q2_03_emergency_distribution", "process", process_emergency, ["emergency_by_hour","emergency_ecdf"], "Histogram and ECDF", "Emergency energy is uneven across time slots and across report days."),
    ("result_q2_01_monthly_cash", "result", result_cost, ["monthly_summary"], "Stacked accounting bars", "Scheduled and emergency cash jointly determine observed monthly operating cost."),
    ("result_q2_02_monthly_risk", "result", result_risk, ["main_daily","monthly_risk"], "Boxplot and frequency points", "The month-specific daily cash tail and emergency frequency vary across the report window."),
    ("result_q2_03_common333_sensitivity", "result", result_sensitivity, ["sensitivity_summary"], "Paired baseline-difference dot plots", "Frozen interpretation sensitivities differ on one common 333-plan-date window."),
]


def contracts(tables, source_manifest):
    output=[]
    for name,category,_,sources,kind,claim in SPECS:
        output.append(dict(figure_id=name,question="q2",category=category,core_conclusion=claim,
            evidence_chain={key: source_manifest["tables"][key] for key in sources},
            archetype="quantitative grid",backend="Python/matplotlib",chart_type=kind,
            alternative="Separate single-panel charts; avoided because the paired panels answer complementary parts of one claim.",
            dimensions="7.2-inch double-column width; exact height recorded in the export manifest",
            fonts="DejaVu Sans; 7-11 pt; editable SVG text and embedded TrueType PDF",
            exports=["PNG 300 dpi","SVG","PDF","grayscale PNG 300 dpi"],
            policy="primary B0; frozen main Time A",report_window="365 raw / 334 main / 333 common sensitivity plan dates",
            statistical_scope="Descriptive observed data; no refitting, new policy metrics, inferential errors or causal claim",
            data_integrity="All rows retained in the stated windows; zero counts and outliers retained. No synthetic observations.",
            exclusions="January is warmup, excluded only from main-report plots; December31 excluded only from common sensitivity.",
            actual_rows={key: len(tables[key]) for key in sources}))
    return output


def export_one(fig, name):
    dimensions=tuple(float(x) for x in fig.get_size_inches())
    preview=FIGURES/"previews"/(name+".png")
    render_preview(fig,str(preview),dpi=150)
    layout=audit_layout(fig)
    if any(severity in ("WARN","FAIL") for severity,_ in layout):
        raise RuntimeError(f"layout audit needs correction for {name}: {layout}")
    footer_audit=audit_footer_spacing(fig)
    paths=export_figure(fig,str(FIGURES/name),formats=["png","svg","pdf"],size_inches=dimensions,
        dpi=300,tight=False,grayscale_preview=False)
    # Preserve exact canvas size and DPI; the unmodified upstream grayscale helper crops PNGs.
    gray=FIGURES/(name+"_grayscale.png")
    with Image.open(FIGURES/(name+".png")) as original:
        original.convert("L").save(gray,dpi=(300,300))
    paths.append(str(gray))
    checks=[]
    for filename in paths:
        issues,info=check_figure(filename,min_dpi=300,target_inches=dimensions)
        checks.append(dict(path=str(Path(filename).relative_to(VERSION)),issues=issues,info=info))
        if any(severity in ("WARN","FAIL") for severity,_ in issues):
            raise RuntimeError(f"file audit needs correction for {filename}: {issues}")
    svg=(FIGURES/(name+".svg")).read_text()
    if "data:image/" in svg or "<text" not in svg:
        raise AssertionError("SVG must contain editable text and no embedded bitmap")
    return dict(dimensions_inches=dimensions,layout_issues=layout,footer_audit=footer_audit,file_checks=checks,
        preview=str(preview.relative_to(VERSION)),visual_review="PENDING_AUTHOR_IMAGE_INSPECTION")


def run(args):
    OTHERS.mkdir(parents=True,exist_ok=True)
    if args.profile_run:
        tables=raw_tables()
        tables["main_daily"],tables["main_interval"]=normalize_main(pd.read_csv(MAIN_RUN/"daily_ledger.csv"),pd.read_csv(MAIN_RUN/"interval_ledger.csv"))
        write_json(OTHERS/"figure_eda.json",profile_inputs(tables))
        print("Profiled original observations and frozen main run; no model or figure replay.")
        return
    if args.from_figure_data:
        tables,data_manifest=load_portable()
    else:
        tables,inputs=load_final(args.source_dir.resolve())
        data_manifest=save_tables(tables,inputs)
    write_json(OTHERS/"figure_eda.json",profile_inputs(tables))
    write_json(OTHERS/"figure_contracts.json",contracts(tables,data_manifest))
    FIGURES.mkdir(parents=True,exist_ok=True)
    sources=source_snapshot()
    manifest=dict(status="running",complete=False,created_at=datetime.now(timezone.utc).isoformat(),
        solver_called=False,training_called=False,annual_replay=False,
        source_hashes=sources,git_source_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        input_hashes=data_manifest["source_input_hashes"],figure_data_hashes=data_manifest["data_hashes"],
        packages={name:importlib.metadata.version(name) for name in ("numpy","pandas","matplotlib","openpyxl","Pillow")},
        policy="B0",main_days=334,sensitivity_common_days=333,time_scope="old Time A plan dates; Time B remains the legacy right-endpoint sensitivity",
        figures={},independent_review="PENDING_OTHER_AGENT")
    write_json(OTHERS/"figure_delivery_manifest.json",manifest)
    setup_style(journal="nature",lang="en",use_sciplots=False,constrained_layout=False)
    plt.rcParams.update({"font.sans-serif":["DejaVu Sans"],"font.size":8,"axes.labelsize":8,
        "legend.fontsize":8,"xtick.labelsize":7,"ytick.labelsize":7,"path.simplify":False})
    try:
        for name,category,draw,_,_,_ in SPECS:
            fig=draw(tables)
            try:
                manifest["figures"][name]={"category":category,**export_one(fig,name)}
            finally:
                plt.close(fig)
            write_json(OTHERS/"figure_delivery_manifest.json",manifest)
        if source_snapshot()!=sources:
            raise RuntimeError("figure source changed during rendering")
        manifest.update(status="complete_pending_visual_review",complete=True,
            category_counts={category:sum(row[1]==category for row in SPECS) for category in ("raw","process","result")})
    except BaseException as exc:
        manifest.update(status="failed",complete=False,error=repr(exc))
        raise
    finally:
        manifest["output_hashes"]=snapshot([p for base in (FIGURES,DATA) for p in base.rglob("*") if p.is_file()])
        write_json(OTHERS/"figure_delivery_manifest.json",manifest)
    print(f"Nine logical figures written to {FIGURES}")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir",type=Path,default=VERSION/"results/final_v1")
    parser.add_argument("--from-figure-data",action="store_true",help="redraw using only the portable plotted-data bundle")
    parser.add_argument("--profile-run",action="store_true",help="EDA only from the frozen run; no final_v1 needed")
    run(parser.parse_args())


if __name__=="__main__":
    main()
