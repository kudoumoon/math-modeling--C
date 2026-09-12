"""Generate publication-ready Q4 figures from validated result logs.

No optimization is rerun.  Every figure is exported as 300-DPI PNG plus
editable SVG and PDF, with source tables and machine layout audits.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TwoSlopeNorm
from matplotlib.ticker import FuncFormatter, MaxNLocator
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
PROGRAM_DIR = Path(__file__).resolve().parent
FIGURE_DIR = ROOT / "Q4" / "figure"
SOURCE_DIR = FIGURE_DIR / "source_data"
AUDIT_DIR = ROOT / "Q4" / "audit" / "figure"
RESULT_DIR = ROOT / "Q4" / "result"
SKILL_SCRIPTS = PROGRAM_DIR / "figure_utils"
if not SKILL_SCRIPTS.is_dir():
    raise FileNotFoundError(f"缺少随项目分发的绘图辅助模块: {SKILL_SCRIPTS}")
sys.path.insert(0, str(SKILL_SCRIPTS))

from export_figure import export_figure
from setup_style import setup_style
from visual_qa import audit_layout, render_preview


COLORS = {
    "q42": "#0072B2",
    "m0": "#999999",
    "m1": "#56B4E9",
    "m2": "#E69F00",
    "m3": "#D55E00",
    "actual": "#222222",
    "forecast": "#0072B2",
    "pv": "#009E73",
    "load": "#D55E00",
    "ordinary": "#0072B2",
    "emergency": "#E69F00",
    "positive": "#009E73",
    "negative": "#CC79A7",
}


def evaluation(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["interval_start"] = pd.to_datetime(frame["interval_start"])
    frame["plan_day"] = pd.to_datetime(frame["plan_day"])
    return frame.loc[
        (frame["plan_day"] >= pd.Timestamp("2025-02-01"))
        & (frame["plan_day"] <= pd.Timestamp("2025-12-31"))
    ].copy()


def wan_formatter(value, _position) -> str:
    return f"{value / 10000:.0f}"


def clock_ticks(ax) -> None:
    ax.set_xticks([0, 35, 71, 107, 143])
    ax.set_xticklabels(["00:10", "06:00", "12:00", "18:00", "次日00:00"])


def clean_axis(ax, grid_axis="y") -> None:
    ax.grid(True, axis=grid_axis, color="#D9D9D9", linewidth=0.5, alpha=0.7)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def save_figure(fig, stem: str, source: pd.DataFrame) -> dict:
    source.to_csv(SOURCE_DIR / f"{stem}.csv", index=False, encoding="utf-8-sig")
    # First let Matplotlib finish its native constrained layout while its axes
    # objects are untouched, then freeze that layout for the compatibility shim.
    fig.canvas.draw()
    fig.set_constrained_layout(False)
    # visual_qa targets newer Matplotlib.  Plain colorbar Axes in 3.5 lacks
    # get_subplotspec; mark it as a non-subplot so the same audit can proceed.
    for axis in fig.axes:
        if not hasattr(axis, "get_subplotspec"):
            axis.get_subplotspec = lambda: None
    issues = audit_layout(fig)
    failures = [message for severity, message in issues if severity == "FAIL"]
    if failures:
        raise AssertionError(f"{stem} layout audit failed: {failures}")
    preview = AUDIT_DIR / f"{stem}_preview.png"
    render_preview(fig, str(preview), dpi=150)
    paths = export_figure(
        fig,
        basename=str(FIGURE_DIR / stem),
        formats=("pdf", "svg", "png"),
        size_inches=(7.2, 4.5),
        dpi=300,
        grayscale_preview=False,
        tight=False,
    )
    gray = AUDIT_DIR / f"{stem}_grayscale.png"
    Image.open(FIGURE_DIR / f"{stem}.png").convert("L").save(gray, dpi=(300, 300))
    plt.close(fig)
    return {"stem": stem, "issues": issues, "files": paths, "source_rows": len(source)}


def load_data():
    q42 = evaluation(pd.read_csv(RESULT_DIR / "q4_2_execution_log.csv", low_memory=False))
    schedules = {
        name: evaluation(pd.read_csv(RESULT_DIR / f"q4_3_{name}_execution_log.csv", low_memory=False))
        for name in ("M0", "M1", "M2", "M3")
    }
    decisions = pd.read_csv(RESULT_DIR / "q4_3_M3_decisions.csv", low_memory=False)
    decisions["day"] = pd.to_datetime(decisions["day"])
    summary = json.loads((RESULT_DIR / "q4_final_summary.json").read_text(encoding="utf-8"))
    oracle = json.loads((RESULT_DIR / "q4_price_oracle_summary.json").read_text(encoding="utf-8"))
    return q42, schedules, decisions, summary, oracle


def raw_price_heatmap(q42):
    pivot = q42.pivot(index="plan_day", columns="step", values="price_actual_yuan_per_kwh").sort_index()
    fig, ax = plt.subplots(figsize=(7.2, 4.5))
    image = ax.imshow(pivot.to_numpy(), aspect="auto", cmap="viridis", interpolation="nearest")
    months = pivot.index.to_series().groupby(pivot.index.month).head(1)
    positions = [pivot.index.get_loc(date) for date in months.index]
    ax.set_yticks(positions)
    ax.set_yticklabels([f"{date.month}月" for date in months.index])
    clock_ticks(ax)
    ax.set_xlabel("日内时段")
    ax.set_ylabel("日期")
    ax.set_title("2025年2—12月动态电价的时空分布")
    bar = fig.colorbar(image, ax=ax, pad=0.02)
    bar.set_label("实际电价（元/kWh）")
    source = pivot.reset_index().melt(id_vars="plan_day", var_name="step", value_name="actual_price_yuan_per_kwh")
    return fig, source


def raw_forecast_actual_hexbin(m3):
    source = m3[["plan_day", "step", "price_forecast_yuan_per_kwh", "price_actual_yuan_per_kwh"]].copy()
    x = source["price_actual_yuan_per_kwh"].to_numpy(float)
    y = source["price_forecast_yuan_per_kwh"].to_numpy(float)
    limit = max(x.max(), y.max())
    fig, ax = plt.subplots(figsize=(7.2, 4.5))
    hb = ax.hexbin(x, y, gridsize=55, bins="log", mincnt=1, cmap="cividis", linewidths=0)
    ax.plot([0, limit], [0, limit], linestyle="--", color="#D55E00", linewidth=1.2, label="理想预测线")
    mae = float(np.mean(np.abs(y - x)))
    rmse = float(np.sqrt(np.mean((y - x) ** 2)))
    ax.text(0.04, 0.95, f"MAE = {mae:.4f} 元/kWh\nRMSE = {rmse:.4f} 元/kWh\nn = {len(source):,}", transform=ax.transAxes, va="top", ha="left", bbox={"boxstyle": "round,pad=0.3", "fc": "white", "ec": "#BBBBBB", "alpha": 0.92})
    ax.set_xlim(0, limit)
    ax.set_ylim(0, limit)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("实际电价（元/kWh）")
    ax.set_ylabel("因果预测电价（元/kWh）")
    ax.set_title("M3执行时点的预测电价与实际电价")
    ax.legend(frameon=False, loc="lower right")
    bar = fig.colorbar(hb, ax=ax, pad=0.02)
    bar.set_label("区间数量（对数色标）")
    clean_axis(ax, grid_axis="both")
    return fig, source


def raw_representative_day(q42):
    volatility = q42.groupby("plan_day")["price_actual_yuan_per_kwh"].std().sort_index()
    target = (volatility - volatility.median()).abs().idxmin()
    one = q42.loc[q42["plan_day"] == target].sort_values("step").copy()
    fig, axes = plt.subplots(2, 1, figsize=(7.2, 4.5), sharex=True, gridspec_kw={"height_ratios": [1.25, 1]})
    axes[0].plot(one["step"], one["load_actual_kwh"], color=COLORS["load"], label="实际负荷", linewidth=1.4)
    axes[0].plot(one["step"], one["pv_actual_kwh"], color=COLORS["pv"], label="实际光伏", linewidth=1.3, linestyle="--")
    axes[0].plot(one["step"], one["plan_grid_kwh"], color=COLORS["q42"], label="计划购电", linewidth=1.1, linestyle="-.")
    axes[0].set_ylabel("电量（kWh/10min）")
    axes[0].legend(frameon=False, ncol=3, loc="upper center")
    axes[0].set_title(f"代表日供需与动态电价（{pd.Timestamp(target):%Y-%m-%d}）")
    axes[1].plot(one["step"], one["price_actual_yuan_per_kwh"], color=COLORS["actual"], label="实际电价", linewidth=1.4)
    axes[1].plot(one["step"], one["price_forecast_yuan_per_kwh"], color=COLORS["forecast"], label="预测电价", linewidth=1.2, linestyle="--")
    axes[1].set_ylabel("电价（元/kWh）")
    axes[1].set_xlabel("日内时段")
    axes[1].legend(frameon=False, ncol=2, loc="upper center")
    clock_ticks(axes[1])
    for ax in axes:
        clean_axis(ax)
    return fig, one[["plan_day", "step", "load_actual_kwh", "pv_actual_kwh", "plan_grid_kwh", "price_actual_yuan_per_kwh", "price_forecast_yuan_per_kwh"]]


def process_soc_heatmap(q42):
    pivot = q42.pivot(index="plan_day", columns="step", values="soc_after_kwh").sort_index()
    fig, ax = plt.subplots(figsize=(7.2, 4.5))
    image = ax.imshow(pivot.to_numpy(), aspect="auto", cmap="magma", vmin=1200, vmax=10800, interpolation="nearest")
    months = pivot.index.to_series().groupby(pivot.index.month).head(1)
    positions = [pivot.index.get_loc(date) for date in months.index]
    ax.set_yticks(positions)
    ax.set_yticklabels([f"{date.month}月" for date in months.index])
    clock_ticks(ax)
    ax.set_xlabel("日内时段")
    ax.set_ylabel("日期")
    ax.set_title("Q4-2连续滚动调度的储能SOC分布")
    bar = fig.colorbar(image, ax=ax, pad=0.02)
    bar.set_label("SOC（kWh）")
    source = pivot.reset_index().melt(id_vars="plan_day", var_name="step", value_name="soc_after_kwh")
    return fig, source


def process_adjustment_heatmap(m3):
    source = m3[["plan_day", "step", "q0_kwh", "qfinal_kwh"]].copy()
    source["adjustment_kwh"] = source["qfinal_kwh"] - source["q0_kwh"]
    pivot = source.pivot(index="plan_day", columns="step", values="adjustment_kwh").sort_index()
    bound = float(np.max(np.abs(pivot.to_numpy())))
    norm = TwoSlopeNorm(vmin=-bound, vcenter=0.0, vmax=bound)
    fig, ax = plt.subplots(figsize=(7.2, 4.5))
    image = ax.imshow(pivot.to_numpy(), aspect="auto", cmap="RdBu_r", norm=norm, interpolation="nearest")
    months = pivot.index.to_series().groupby(pivot.index.month).head(1)
    positions = [pivot.index.get_loc(date) for date in months.index]
    ax.set_yticks(positions)
    ax.set_yticklabels([f"{date.month}月" for date in months.index])
    clock_ticks(ax)
    ax.set_xlabel("日内时段")
    ax.set_ylabel("日期")
    ax.set_title("M3最终合同相对00:00原合同的调整分布")
    bar = fig.colorbar(image, ax=ax, pad=0.02)
    bar.set_label("调整量 qfinal-q0（kWh）")
    return fig, source


def process_release_acceptance(decisions):
    source = decisions.groupby("release_hour", as_index=False).agg(
        decisions=("accepted", "size"),
        accepted=("accepted", "sum"),
        changed_intervals=("changed_intervals", "sum"),
    )
    source["acceptance_rate"] = source["accepted"] / source["decisions"]
    labels = [f"{int(hour):02d}:00" for hour in source["release_hour"]]
    fig, ax = plt.subplots(figsize=(7.2, 4.5))
    bars = ax.barh(labels, source["acceptance_rate"] * 100, color=[COLORS["m1"], COLORS["m2"], COLORS["m3"]], height=0.58)
    for bar, row in zip(bars, source.itertuples()):
        ax.text(bar.get_width() + 1.0, bar.get_y() + bar.get_height() / 2, f"{int(row.accepted)}/{int(row.decisions)}，改变{int(row.changed_intervals)}段", va="center", fontsize=8)
    ax.set_xlim(0, max(75, float((source["acceptance_rate"] * 100).max() + 18)))
    ax.set_xlabel("经济门接受率（%）")
    ax.set_ylabel("信息发布时间")
    ax.set_title("M3各发布时刻的合同更新接受情况")
    clean_axis(ax, grid_axis="x")
    return fig, source


def result_q42_oracle(summary, oracle):
    source = pd.DataFrame({
        "scheme": ["因果价格预测", "完全电价信息Oracle"],
        "total_cost_yuan": [summary["q4_2"]["total_cash_yuan"], oracle["q4_2"]["total_cash_yuan"]],
    })
    fig, ax = plt.subplots(figsize=(7.2, 4.5))
    bars = ax.bar(source["scheme"], source["total_cost_yuan"], color=[COLORS["q42"], COLORS["positive"]], width=0.58)
    ax.set_ylim(0, source["total_cost_yuan"].max() * 1.16)
    for bar, value in zip(bars, source["total_cost_yuan"]):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.015 * source["total_cost_yuan"].max(), f"{value/10000:.2f}万元", ha="center", va="bottom", fontsize=9)
    gap = float(source.iloc[0, 1] - source.iloc[1, 1])
    ax.text(0.5, 0.88, f"电价信息差额：{gap/10000:.2f}万元（{gap/source.iloc[0,1]*100:.2f}%）", transform=ax.transAxes, ha="center", color="#333333")
    ax.set_ylabel("全年总费用（万元）")
    ax.yaxis.set_major_formatter(FuncFormatter(wan_formatter))
    ax.set_title("Q4-2因果方案与完全电价信息上界")
    clean_axis(ax)
    return fig, source


def result_strategy_components(summary):
    rows = []
    for name in ("M0", "M1", "M2", "M3"):
        item = summary["q4_3"][name]
        rows.append({"strategy": name, "ordinary_cost_yuan": item["ordinary_cost_B_yuan"], "emergency_cost_yuan": item["emergency_cost_yuan"], "total_cost_yuan": item["total_cash_B_yuan"]})
    source = pd.DataFrame(rows)
    x = np.arange(len(source))
    fig, ax = plt.subplots(figsize=(7.2, 4.5))
    ax.bar(x, source["ordinary_cost_yuan"], color=COLORS["ordinary"], label="普通合同费用", width=0.62)
    ax.bar(x, source["emergency_cost_yuan"], bottom=source["ordinary_cost_yuan"], color=COLORS["emergency"], label="应急购电费用", width=0.62)
    for i, total in enumerate(source["total_cost_yuan"]):
        ax.text(i, total + 0.012 * source["total_cost_yuan"].max(), f"{total/10000:.1f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(source["strategy"])
    ax.set_ylim(0, source["total_cost_yuan"].max() * 1.13)
    ax.set_xlabel("信息更新策略")
    ax.set_ylabel("全年费用（万元）")
    ax.yaxis.set_major_formatter(FuncFormatter(wan_formatter))
    ax.set_title("Q4-3不同信息更新策略的费用构成")
    ax.legend(frameon=False, ncol=2, loc="upper right")
    clean_axis(ax)
    return fig, source


def daily_cost(frame):
    frame = frame.copy()
    frame["total_cost_yuan"] = frame["ordinary_cost_B_yuan"] + frame["emergency_cost_yuan"]
    return frame.groupby("plan_day", as_index=False)["total_cost_yuan"].sum().sort_values("plan_day")


def result_cumulative_saving(schedules):
    m0 = daily_cost(schedules["M0"]).rename(columns={"total_cost_yuan": "m0_cost_yuan"})
    m3 = daily_cost(schedules["M3"]).rename(columns={"total_cost_yuan": "m3_cost_yuan"})
    source = m0.merge(m3, on="plan_day", validate="one_to_one")
    source["daily_saving_yuan"] = source["m0_cost_yuan"] - source["m3_cost_yuan"]
    source["cumulative_saving_yuan"] = source["daily_saving_yuan"].cumsum()
    fig, ax = plt.subplots(figsize=(7.2, 4.5))
    ax.plot(source["plan_day"], source["cumulative_saving_yuan"], color=COLORS["m3"], linewidth=1.7, label="M3相对M0累计节省")
    ax.fill_between(source["plan_day"], 0, source["cumulative_saving_yuan"], where=source["cumulative_saving_yuan"] >= 0, color=COLORS["m3"], alpha=0.16)
    ax.axhline(0, color="#777777", linewidth=0.8)
    final = float(source["cumulative_saving_yuan"].iloc[-1])
    ax.scatter(source["plan_day"].iloc[-1], final, color=COLORS["m3"], s=28, zorder=3)
    ax.annotate(f"全年节省 {final/10000:.2f} 万元", xy=(source["plan_day"].iloc[-1], final), xytext=(-105, -4), textcoords="offset points", va="center", arrowprops={"arrowstyle": "->", "color": COLORS["m3"], "lw": 0.8})
    ax.set_xlabel("日期")
    ax.set_ylabel("累计节省（万元）")
    ax.yaxis.set_major_formatter(FuncFormatter(wan_formatter))
    ax.set_title("M3相对M0的全年累计费用优势")
    ax.legend(frameon=False, loc="upper left")
    clean_axis(ax)
    return fig, source


def main() -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    chosen_font = setup_style(journal="general", lang="zh", serif_for_zh=True, use_sciplots=False)
    plt.rcParams.update({
        "figure.constrained_layout.use": True,
        "axes.unicode_minus": False,
        "pdf.fonttype": 42,
        "svg.fonttype": "none",
    })
    q42, schedules, decisions, summary, oracle = load_data()
    contracts = [
        ("raw_q1_q42_price_heatmap", raw_price_heatmap(q42)),
        ("raw_q2_q43_price_forecast_actual", raw_forecast_actual_hexbin(schedules["M3"])),
        ("raw_q1_q42_representative_day", raw_representative_day(q42)),
        ("process_q1_q42_soc_heatmap", process_soc_heatmap(q42)),
        ("process_q2_q43_adjustment_heatmap", process_adjustment_heatmap(schedules["M3"])),
        ("process_q2_q43_release_acceptance", process_release_acceptance(decisions)),
        ("result_q1_q42_oracle_comparison", result_q42_oracle(summary, oracle)),
        ("result_q2_q43_cost_components", result_strategy_components(summary)),
        ("result_q2_q43_cumulative_saving", result_cumulative_saving(schedules)),
    ]
    reports = []
    for stem, (fig, source) in contracts:
        reports.append(save_figure(fig, stem, source))
    audit = {
        "status": "PASS",
        "font": chosen_font,
        "figures": reports,
        "figure_count": len(reports),
        "formats": ["png", "svg", "pdf"],
        "dpi": 300,
    }
    (AUDIT_DIR / "q4_figure_generation_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"status": "PASS", "font": chosen_font, "figures": len(reports)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
