from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


SLOTS_PER_DAY = 144
STEP = pd.Timedelta(minutes=10)


@dataclass(frozen=True)
class ProblemData:
    load: pd.DataFrame
    pv_actual: pd.DataFrame
    price: pd.DataFrame
    pv_forecasts: pd.DataFrame


def _read_daily_matrix(path: Path, sheet_name: str | int) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=sheet_name)
    if raw.shape[1] != SLOTS_PER_DAY + 1:
        raise ValueError(f"{path}/{sheet_name}: expected 145 columns, got {raw.shape[1]}")
    dates = pd.to_datetime(raw.iloc[:, 0], errors="raise").dt.normalize()
    values = raw.iloc[:, 1:].apply(pd.to_numeric, errors="raise").astype(float)
    values.index = pd.DatetimeIndex(dates, name="date")
    values.columns = pd.RangeIndex(SLOTS_PER_DAY, name="slot")
    if values.index.has_duplicates or not values.index.is_monotonic_increasing:
        raise ValueError(f"{path}/{sheet_name}: dates must be unique and increasing")
    if values.isna().any().any():
        raise ValueError(f"{path}/{sheet_name}: missing values are not permitted")
    return values


def daily_to_long(values: pd.DataFrame, value_name: str) -> pd.DataFrame:
    """Map row d to starts d+00:10, ..., d+1 00:00, per the frozen protocol."""
    stacked = values.stack().rename(value_name).reset_index()
    stacked.columns = ["date", "slot", value_name]
    stacked["interval_start"] = (
        stacked["date"] + pd.to_timedelta((stacked["slot"] + 1) * 10, unit="min")
    )
    stacked["interval_end"] = stacked["interval_start"] + STEP
    if stacked["interval_start"].duplicated().any():
        raise ValueError("constructed interval_start contains duplicates")
    expected = pd.date_range(
        stacked["interval_start"].min(), stacked["interval_start"].max(), freq=STEP
    )
    if len(expected) != len(stacked) or not np.array_equal(
        expected.values, stacked["interval_start"].values
    ):
        raise ValueError("constructed time axis has a gap or ordering error")
    return stacked


def _read_pv_forecasts(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path)
    raw["日期"] = pd.to_datetime(raw["日期"].ffill(), errors="raise").dt.normalize()
    issue_delta = pd.to_timedelta(raw["预报时刻"].astype(str) + ":00")
    issue_time = raw["日期"] + issue_delta
    value_cols = [f"预报{i}小时" for i in range(1, 25)]
    long = raw.assign(issue_time=issue_time).melt(
        id_vars=["issue_time"], value_vars=value_cols, var_name="lead_label", value_name="raw_pv"
    )
    long["lead_hour"] = long["lead_label"].str.extract(r"(\d+)").astype(int)
    long["window_start"] = long["issue_time"] + pd.to_timedelta(
        long["lead_hour"] - 1, unit="h"
    ) + STEP
    long["window_end"] = long["issue_time"] + pd.to_timedelta(long["lead_hour"], unit="h") + STEP
    long["target_time"] = long["issue_time"] + pd.to_timedelta(long["lead_hour"], unit="h")
    long["issue_hour"] = long["issue_time"].dt.hour
    return long.drop(columns="lead_label").sort_values(["issue_time", "lead_hour"]).reset_index(drop=True)


def _attach_hourly_pv_actual(forecasts: pd.DataFrame, pv_actual: pd.DataFrame) -> pd.DataFrame:
    pv_long = daily_to_long(pv_actual, "pv_actual")[["interval_start", "pv_actual"]]
    lookup = pv_long.set_index("interval_start")["pv_actual"]
    out = forecasts.copy()
    actual = []
    observed_count = []
    for row in out.itertuples(index=False):
        starts = pd.date_range(row.window_start, periods=6, freq=STEP)
        vals = lookup.reindex(starts)
        actual.append(vals.mean() if vals.notna().all() else np.nan)
        observed_count.append(int(vals.notna().sum()))
    out["actual_pv"] = actual
    out["actual_intervals"] = observed_count
    return out


def load_problem_data(root: str | Path = ".") -> ProblemData:
    root = Path(root)
    attachment2 = root / "data" / "附件2.xlsx"
    load = _read_daily_matrix(attachment2, "小区负载")
    pv_actual = _read_daily_matrix(attachment2, "光伏发电实际功率")
    price = _read_daily_matrix(root / "data" / "附件4.xlsx", 0)
    if not load.index.equals(pv_actual.index) or not load.index.equals(price.index):
        raise ValueError("load, PV, and price date indexes do not agree")
    pv_forecasts = _attach_hourly_pv_actual(
        _read_pv_forecasts(root / "data" / "附件3.xlsx"), pv_actual
    )
    return ProblemData(load=load, pv_actual=pv_actual, price=price, pv_forecasts=pv_forecasts)

