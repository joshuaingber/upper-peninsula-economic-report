"""
Analytical computations: STL trend decomposition + linear trend projection.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL


_QUARTER_TO_MONTH = {1: 2, 2: 5, 3: 8, 4: 11}


def _next_quarter_dates(last_date: pd.Timestamp, periods: int) -> pd.DatetimeIndex:
    """Generate the next `periods` mid-quarter dates after `last_date`.

    Mirrors data/clean.py's quarter-to-month convention (Q1→Feb, Q2→May,
    Q3→Aug, Q4→Nov) so projected points line up with the actual quarter grid.
    """
    year = int(last_date.year)
    qtr = {2: 1, 5: 2, 8: 3, 11: 4}[int(last_date.month)]
    out = []
    for _ in range(periods):
        qtr += 1
        if qtr > 4:
            qtr = 1
            year += 1
        out.append(pd.Timestamp(year=year, month=_QUARTER_TO_MONTH[qtr], day=1))
    return pd.DatetimeIndex(out)


def periods_to_current_quarter(last_trend_date: pd.Timestamp,
                               today: pd.Timestamp | None = None) -> int:
    """Number of quarters from `last_trend_date` to the current calendar quarter.

    Returns 0 if the trend already reaches (or exceeds) the current quarter.
    Used by trend-chart callers to set the projection horizon dynamically:
    the projection always extends through the current calendar quarter.

    >>> periods_to_current_quarter(pd.Timestamp("2025-08-01"), pd.Timestamp("2026-05-12"))
    3
    >>> periods_to_current_quarter(pd.Timestamp("2025-08-01"), pd.Timestamp("2025-08-15"))
    0
    >>> periods_to_current_quarter(pd.Timestamp("2025-11-01"), pd.Timestamp("2026-02-15"))
    1
    >>> periods_to_current_quarter(pd.Timestamp("2025-08-01"), pd.Timestamp("2024-01-01"))
    0
    """
    today = pd.Timestamp.today() if today is None else today
    diff = (today.to_period("Q") - last_trend_date.to_period("Q")).n
    return max(0, diff)


def project_trend(
    trend: pd.Series,
    periods: int = 2,
    lookback: int = 4,
    log_transform: bool = False,
) -> pd.Series:
    """Linear-extrapolation projection of a trend series.

    Fits OLS to the last `lookback` non-NaN points (in log space if requested)
    and returns the next `periods` projected values, indexed at the next
    `periods` quarter dates after the trend's last observation.

    Returns an empty Series if there are fewer than `lookback` valid trend points.
    """
    s = trend.dropna().sort_index()
    if len(s) < lookback:
        return pd.Series(dtype=float)

    tail = s.tail(lookback)
    x = np.arange(len(tail))
    y = np.log(tail.values) if log_transform else tail.values
    slope, intercept = np.polyfit(x, y, 1)

    future_x = np.arange(len(tail), len(tail) + periods)
    future_y = slope * future_x + intercept
    if log_transform:
        future_y = np.exp(future_y)

    return pd.Series(future_y, index=_next_quarter_dates(tail.index[-1], periods))


def deseasonalize_trend(
    series: pd.Series,
    period: int = 4,
    seasonal: int = 7,
    log_transform: bool = False,
) -> pd.Series:
    """STL trend component for a quarterly series.

    Falls back to the raw series when there are fewer than 2*period
    observations (STL requires at least two full cycles).

    Use log_transform=True for multiplicatively-growing series like wages —
    a $500 seasonal swing means different things at $45k vs $65k base.
    """
    s = series.dropna().sort_index()
    s = s[~s.index.duplicated(keep="last")]
    if len(s) < 2 * period:
        return series.copy()

    work = np.log(s) if log_transform else s
    result = STL(work, period=period, seasonal=seasonal, robust=True).fit()
    trend = np.exp(result.trend) if log_transform else result.trend
    return trend.reindex(series.index)
