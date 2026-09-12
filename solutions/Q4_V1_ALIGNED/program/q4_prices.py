"""Frozen lag-seven price forecasts with explicit observation completion times."""
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PriceForecast:
    values: np.ndarray
    source_completed_at: pd.DatetimeIndex
    model_id: str
    issue_time: pd.Timestamp


def load_prices(path, dates):
    frame = pd.read_excel(path)
    observed_dates = pd.DatetimeIndex(pd.to_datetime(frame.iloc[:, 0]))
    values = frame.iloc[:, 1:].to_numpy(float)
    if not observed_dates.equals(dates) or not dates.is_unique or not dates.is_monotonic_increasing:
        raise ValueError("attachment 4 dates must match unique ordered attachment 2 dates")
    if values.shape != (len(dates), 144) or not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("invalid dynamic price observations")
    return values


def forecast_prices(dates, actual_prices, prior_prices, day, issue_time):
    issue = pd.Timestamp(issue_time)
    if issue != dates[day] + pd.Timedelta(hours=issue.hour) or issue.hour not in (0, 6, 12, 18):
        raise ValueError("price issue must be 00/06/12/18 on the target day")
    if day < 7:
        values = np.array(prior_prices, dtype=float, copy=True)
        sources = pd.DatetimeIndex([dates[0] - pd.Timedelta(days=1)] * 144)
        model_id = "ATTACHMENT1-DECLARED-PRIOR"
    else:
        sources = dates[day - 7] + pd.to_timedelta((np.arange(144) + 2) * 10, unit="min")
        if (sources > issue).any():
            raise ValueError("uncompleted price source")
        values = np.array(actual_prices[day - 7], dtype=float, copy=True)
        model_id = "PRICE-LAG7-COMPLETED"
    if values.shape != (144,) or not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("invalid price forecast")
    values.flags.writeable = False
    return PriceForecast(values, sources, model_id, issue)
