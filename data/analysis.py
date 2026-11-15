# Trend analysis helpers for quarterly series: removes seasonality to reveal the
# underlying trend, and projects that trend forward a few quarters.
"""
Analytical computations: STL trend decomposition + linear trend projection.

The trend comes from statsmodels' STL decomposition. The projection is a
straight-line fit to the last few trend points, extended along the project's
quarterly date grid.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL


# Maps a quarter number to its mid-quarter month. This duplicates
# QUARTER_TO_MONTH in data/clean.py, so keep the two in sync.
_QUARTER_TO_MONTH = {1: 2, 2: 5, 3: 8, 4: 11}


# Returns the next `periods` mid-quarter dates after `last_date`, following the
# project's convention so projected points line up with the actual quarter grid.
def _next_quarter_dates(last_date: pd.Timestamp, periods: int) -> pd.DatetimeIndex:
    """Convert last_date's month back to a quarter, then step forward one quarter at a time.

    Mirrors data/clean.py's quarter-to-month convention (Q1→Feb, Q2→May,
    Q3→Aug, Q4→Nov). The month is mapped back to a quarter (2→1, 5→2, 8→3,
    11→4), so a date in any other month raises a KeyError. Each step adds one
    quarter and rolls the year over after Q4, then builds a Timestamp on the
    1st of that quarter's mapped month.
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


# Returns how many quarters lie between the last trend date and the current
# calendar quarter, or 0 if the trend already reaches it. Trend-chart callers
# use this to set the projection horizon dynamically, so the projection always
# extends through the current calendar quarter.
def periods_to_current_quarter(last_trend_date: pd.Timestamp,
                               today: pd.Timestamp | None = None) -> int:
    """Subtract the two dates' quarterly periods and clamp negative results to 0.

    `today` defaults to the current date (pd.Timestamp.today()) and can be
    passed in to make the result predictable, as in the examples below. Both
    dates are converted with to_period("Q"), and the .n attribute of their
    difference is the number of quarters.

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


# Projects a trend series forward by fitting a straight line to its last few
# points. Returns the projected values on the next quarter dates, or an empty
# Series if there are fewer than `lookback` valid points.
def project_trend(
    trend: pd.Series,
    periods: int = 2,
    lookback: int = 4,
    log_transform: bool = False,
) -> pd.Series:
    """Fit a line to the last `lookback` points and extend it `periods` steps.

    Drops NaN values and sorts by index, then fits a degree-1 polynomial
    (OLS) with np.polyfit, using each point's position (0, 1, 2, ...) as x, so
    it assumes evenly spaced quarters. With log_transform=True the fit is done
    on log values, which must be positive, and the projection is converted
    back with np.exp. The result is indexed at the next `periods` quarter
    dates after the trend's last observation (see _next_quarter_dates).
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


# Returns the trend component of a quarterly series, meaning the series with
# its seasonal swings removed, aligned to the input's original index.
def deseasonalize_trend(
    series: pd.Series,
    period: int = 4,
    seasonal: int = 7,
    log_transform: bool = False,
) -> pd.Series:
    """Run an STL decomposition and return its trend, reindexed to the input.

    Drops NaN values, sorts by index, and removes duplicate index entries
    (keeping the last). Falls back to a copy of the raw series when there are
    fewer than 2*period observations (STL requires at least two full cycles).
    Otherwise it fits STL with the given period and seasonal smoother length,
    using robust=True to reduce the influence of outliers, then reindexes the
    trend to the original series' index, so dropped NaN rows stay NaN.

    Use log_transform=True for multiplicatively-growing series like wages —
    a $500 seasonal swing means different things at $45k vs $65k base. The
    series is logged before STL and the trend is converted back with np.exp.
    """
    s = series.dropna().sort_index()
    s = s[~s.index.duplicated(keep="last")]
    if len(s) < 2 * period:
        return series.copy()

    work = np.log(s) if log_transform else s
    result = STL(work, period=period, seasonal=seasonal, robust=True).fit()
    trend = np.exp(result.trend) if log_transform else result.trend
    return trend.reindex(series.index)

# function takes risk_score from cleaned MIT_AI_safety_sector_rating.csv
# and number of workers from qcew_data.parquet, and returns a df with features: target_code, risk_score, number_of_workers.
# Then creates a new column called weighted_score which is the product of risk_score and number_of_workers.
def merge_mit_ai_safety_sector_rating_with_qcew(df1: pd.DataFrame, df2: pd.DataFrame) -> pd.DataFrame:
    df = df1.merge(
        df2,
        how="inner",
        on="target_code",
        validate="one_to_many",
    )
    df["weighted_score"] = df["risk_score"] * df["number_of_workers"]
    return df