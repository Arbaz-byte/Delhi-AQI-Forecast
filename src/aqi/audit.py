"""Utilities for validating and diagnosing environmental time series.

The helpers cover hourly data loading and structure checks, missing values and
range violations, constant runs, calendar features, wind analysis, and simple
time-series diagnostics such as anomalies and level shifts. They are intended
for reuse across weather, air-quality, and related environmental datasets.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence
import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

# Local Delhi seasons (differ from the IMD calendar on purpose; see notebook).

# Pre-Monsoon - Summer
# Post-Monsoon - Winter
SEASON_BY_MONTH = {
    12: "Winter", 1: "Winter", 2: "Winter",
    3: "Pre-monsoon", 4: "Pre-monsoon", 5: "Pre-monsoon", 6: "Pre-monsoon",
    7: "Monsoon", 8: "Monsoon", 9: "Monsoon",
    10: "Post-monsoon", 11: "Post-monsoon",
}
SEASON_ORDER = ["Winter", "Pre-monsoon", "Monsoon", "Post-monsoon"]
MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

COMPASS_16 = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
WIND_SPEED_BINS = [0, 5, 10, 20, 30, np.inf]
WIND_SPEED_LABELS = ["0–<5", "5–<10", "10–<20", "20–<30", "30+"]


# --------------------------------------------------------------------------
# Loading and structure
# --------------------------------------------------------------------------


def load_hourly(path: str | Path) -> pd.DataFrame:
    """Read an hourly Parquet file and use its ``time`` column as the index.
    
    Parameters
    ----------
    path : str or pathlib.Path
        Path to a Parquet file containing a ``time`` column.
    Returns
    -------
    pandas.DataFrame
        The file contents with ``time`` converted to a ``DatetimeIndex`` named
        ``time``. All other columns are preserved.
        
    Raises
    ------
    ValueError
        If the file contains no rows or has no ``time`` column.
        
    Notes
    -----
    The input order is preserved. The function does not sort timestamps, so
    ``check_structure`` can detect ordering problems.
    """
    df = pd.read_parquet(path)
    
    if df.empty:
        raise ValueError(f"No rows found in {path}")
    if "time" not in df.columns:
        raise ValueError("Parquet data has no 'time' column")
    
    df.index = pd.DatetimeIndex(pd.to_datetime(df.pop("time")), name="time")
    return df


def check_structure(df: pd.DataFrame) -> pd.DataFrame:
    """
    Validate that a frame has a unique, increasing, complete hourly index.
    
    Parameters
    ----------
    df : pandas.DataFrame
        Frame whose index is expected to be a ``DatetimeIndex`` with one-hour
        spacing.
        
    Returns
    -------
    pandas.DataFrame
        One-column summary indexed by ``rows``, ``first``, ``last``,
        ``years_covered``, ``timezone``, ``duplicates``, and ``gaps``.
        
    Raises
    ------
    TypeError
        If the index is not a ``DatetimeIndex``.
    ValueError
        If timestamps are duplicated, out of order, or not exactly one hour
        apart.
    IndexError
        If the index is empty.
        
    Notes
    -----
    Naive timestamps are reported as local IST; timezone-aware indexes report
    their timezone. The input frame is not modified.
    """
    idx = df.index
    
    if not isinstance(idx, pd.DatetimeIndex):
        raise TypeError("Index must be a DatetimeIndex")
    if idx.has_duplicates:
        raise ValueError(f"{idx.duplicated().sum()} duplicate timestamps")
    if not idx.is_monotonic_increasing:
        raise ValueError("Index is not monotonic increasing")

    steps = idx.to_series().diff().iloc[1:]
    bad = steps[steps != pd.Timedelta(hours=1)]
    if not bad.empty:
        raise ValueError(f"{len(bad)} gaps; first: {bad.head(3).to_dict()}")
    
    expected = int((idx[-1] - idx[0]) / pd.Timedelta(hours=1)) + 1
    if expected != len(idx):
        raise ValueError(f"Expected {expected} rows, found {len(idx)}")

    return pd.DataFrame(
        {
            "rows": [len(idx)],
            "first": [idx[0]],
            "last": [idx[-1]],
            "years_covered": [round(len(idx) / 8766, 2)],
            "timezone": [str(idx.tz) if idx.tz else "naive (local IST)"],
            "duplicates": [0],
            "gaps": [0],
        }
    ).T.rename(columns={0: "value"})


def missing_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Count missing values and common sentinels in numeric columns.
    
    Parameters
    ----------
    df : pandas.DataFrame
        Frame containing data columns to inspect. Non-numeric columns are
        ignored.
        
    Returns
    -------
    pandas.DataFrame
        A row per numeric column with ``nan`` and ``sentinel`` counts. The
        recognized sentinels are ``-9999``, ``-999``, and ``9999``.
    """
    sentinels = [-9999, -999, 9999]
    numeric = df.select_dtypes("number")
    return pd.DataFrame(
        {
            "nan": numeric.isna().sum(),
            "sentinel": numeric.isin(sentinels).sum(),
        }
    )


# --------------------------------------------------------------------------
# Ranges and runs
# --------------------------------------------------------------------------

def range_violations( df: pd.DataFrame, ranges: Mapping[str, tuple[float | None, float | None]],) -> pd.DataFrame:
    """Count numeric values strictly outside configured review ranges.
    
    Parameters
    ----------
    df : pandas.DataFrame
        Data containing the variables to check.
    ranges : mapping of str to (float or None, float or None)
        Column names mapped to inclusive lower and upper review bounds. Use
        ``None`` for an unbounded side.
        
    Returns
    -------
    pandas.DataFrame
        One row per requested variable, indexed by variable name, with the
        configured range, counts below and above it, and observed minimum and
        maximum. Missing values are not counted as violations.
        
    Raises
    ------
    KeyError
        If a requested variable is not a column in ``df``.
    """
    rows = []
    for column, (lower, upper) in ranges.items():
        values = df[column]
        low = int((values < lower).sum()) if lower is not None else 0
        high = int((values > upper).sum()) if upper is not None else 0
        rows.append(
            {
                "variable": column,
                "review_range": f"{lower} to {upper}",
                "below": low,
                "above": high,
                "min": values.min(),
                "max": values.max(),
            }
        )
    return pd.DataFrame(rows).set_index("variable")


def constant_runs(series: pd.Series, min_hours: int = 24) -> pd.DataFrame:
    """Find consecutive runs of identical non-missing values.

    Parameters
    ----------
    series : pandas.Series
        Values to inspect, usually an hourly time series.
    min_hours : int, default=24
        Minimum number of consecutive rows required for a run to be returned.
        Despite the parameter name, duration is counted in rows; timestamps
        are not checked for hourly spacing.

    Returns
    -------
    pandas.DataFrame
        Matching runs with ``value``, ``start``, ``end``, and ``hours``
        columns, sorted from longest to shortest. An empty frame is returned
        when no run meets the threshold.

    Notes
    -----
    Missing values break runs and are never treated as repeated values.
    """
    values = series
    same = values.eq(values.shift()) & values.notna() & values.shift().notna()
    run_id = (~same).cumsum()
    
    runs = (
        pd.DataFrame(
            {"value": values.to_numpy(), "time": values.index,
            "run_id": run_id.to_numpy()}
        )
        .dropna(subset=["value"])
        .groupby("run_id")
        .agg(value=("value", "first"), start=("time", "first"),
            end=("time", "last"), hours=("value", "size"))
    )
    
    return (
        runs[runs["hours"] >= min_hours]
        .sort_values("hours", ascending=False)
        .reset_index(drop=True)
    )


# --------------------------------------------------------------------------
# Calendar and seasons
# --------------------------------------------------------------------------

def add_calendar(df: pd.DataFrame) -> pd.DataFrame:
    """Add local calendar and Delhi-season features to a time-indexed frame.
    
    Parameters
    ----------
    df : pandas.DataFrame
        Frame with a datetime-like index.

    Returns
    -------
    pandas.DataFrame
        A copy of ``df`` with ``month``, ``hour``, ``season``, and
        ``season_year`` columns. ``season`` is an ordered categorical using
        ``SEASON_ORDER``.

    Notes
    -----
    December is assigned to the following ``season_year`` so December,
    January, and February belong to the same winter. Existing columns with
    these feature names are replaced in the returned copy; ``df`` is unchanged.
    """
    out = df.copy()
    out["month"] = out.index.month
    out["hour"] = out.index.hour
    out["season"] = pd.Categorical(
        out["month"].map(SEASON_BY_MONTH), categories=SEASON_ORDER, ordered=True
    )
    out["season_year"] = out.index.year + (out["month"] == 12).astype(int)
    return out


def expected_hours_in_year(year: int) -> int:
    """Return the number of hourly observations in a calendar year.

    Parameters
    ----------
    year : int
        Gregorian calendar year.

    Returns
    -------
    int
        ``8760`` for a common year or ``8784`` for a leap year.
    """
    return (366 if pd.Timestamp(year=year, month=1, day=1).is_leap_year else 365) * 24


# --------------------------------------------------------------------------
# Wind
# --------------------------------------------------------------------------

def wind_components(speed: pd.Series, direction: pd.Series) -> pd.DataFrame:
    """Convert meteorological wind speed and direction to east/north components.

    Parameters
    ----------
    speed : pandas.Series
        Wind speed values. Units are preserved in the resulting components.
    direction : pandas.Series
        Meteorological direction in degrees, measured clockwise from north and
        indicating where the wind comes from. It should align with ``speed``.

    Returns
    -------
    pandas.DataFrame
        ``u`` (eastward) and ``v`` (northward) components, indexed like
        ``speed``. The calculation is ``u = -speed * sin(direction)`` and
        ``v = -speed * cos(direction)`` after converting degrees to radians.

    Notes
    -----
    Calm values (speed equal to zero) yield zero components regardless of
    direction. Missing or misaligned values follow pandas' normal alignment
    and missing-value behavior.
    """
    rad = np.deg2rad(direction)

    return pd.DataFrame(
        {"u": -speed * np.sin(rad), "v": -speed * np.cos(rad)},
        index=speed.index,
    )


def wind_rose_table( speed: pd.Series, direction: pd.Series, normalise: bool = True ) -> pd.DataFrame:
    """Tabulate wind observations by compass sector and speed bin.

    Parameters
    ----------
    speed : pandas.Series
        Wind speeds in km/h, matching the bins in ``WIND_SPEED_BINS``.
    direction : pandas.Series
        Meteorological direction in degrees. Values are wrapped modulo 360.
    normalise : bool, default=True
        If true, return percentages of retained observations; otherwise return
        integer counts.

    Returns
    -------
    pandas.DataFrame
        A 16-row compass-sector by 5-column speed-bin table. Missing pairs,
        zero-speed calm observations, and non-positive speeds are excluded.

    Notes
    -----
    The speed bins are left-closed: ``[0, 5)``, ``[5, 10)``, ``[10, 20)``,
    ``[20, 30)``, and ``[30, infinity)``. Direction 360 degrees wraps to north.
    """
    wind = pd.DataFrame({"s": speed, "d": direction}).dropna()
    wind = wind[wind["s"] > 0]
    
    sector = np.floor((wind["d"] % 360 + 11.25) / 22.5).astype(int) % 16
    sector = pd.Categorical.from_codes(sector, categories=COMPASS_16)
    speed_bin = pd.cut(wind["s"], bins=WIND_SPEED_BINS,
                    labels=WIND_SPEED_LABELS, right=False)

    table = (
        pd.crosstab(sector, speed_bin)
        .reindex(index=COMPASS_16, columns=WIND_SPEED_LABELS, fill_value=0)
    )
    return table / len(wind) * 100 if normalise else table


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------

def deseasonalise(series: pd.Series) -> pd.Series:
    """Subtract the mean for each calendar-month and hour-of-day group.

    Parameters
    ----------
    series : pandas.Series
        Time-indexed values with a datetime-like index.

    Returns
    -------
    pandas.Series
        Residuals after subtracting each observation's month-by-hour mean.
        The original index and name are preserved.
    """
    key = [series.index.month, series.index.hour]
    return series - series.groupby(key).transform("mean")


def autocorrelation(series: pd.Series, lags: Sequence[int]) -> pd.Series:
    """Calculate Pearson autocorrelation for requested observation lags.

    Parameters
    ----------
    series : pandas.Series
        Ordered time-series values. For hourly data, lags are measured in
        hours; otherwise they count rows.
    lags : sequence of int
        Integer lag values to evaluate.

    Returns
    -------
    pandas.Series
        Autocorrelation values indexed by the requested lags. Values may be
        ``NaN`` when a lag cannot be calculated, such as for constant data.
    """
    return pd.Series({lag: series.autocorr(lag=lag) for lag in lags})


# --------------------------------------------------------------------------
# Stability / level shifts
# --------------------------------------------------------------------------

def daily_anomaly(series: pd.Series, baseline_end: str) -> pd.Series:
    """Compute daily-mean anomalies against a baseline day-of-year climatology.

    Parameters
    ----------
    series : pandas.Series
        Time-indexed observations to resample to daily means.
    baseline_end : str
        Inclusive end date for fitting the climatology. Later observations do
        not contribute to the baseline.

    Returns
    -------
    pandas.Series
        Daily means minus the corresponding smoothed baseline climatology,
        indexed by day. Days whose day-of-year is absent from the baseline
        produce ``NaN`` anomalies.

    Notes
    -----
    The climatology groups baseline daily means by day of year and smooths
    those means with a centered 15-day rolling window.
    """
    daily = series.resample("D").mean()
    base = daily.loc[:baseline_end]
    clim = (
        base.groupby(base.index.day_of_year).mean()
        .rolling(15, center=True, min_periods=1).mean()
    )
    return daily - clim.reindex(daily.index.day_of_year).to_numpy()


def find_level_shift(
    series: pd.Series,
    start: str,
    end: str,
    min_segment: int = 20,
) -> tuple[pd.Timestamp, float, float]:
    """
    Find the single least-squares change point in the mean within a time window.

    Parameters
    ----------
    series : pandas.Series
        Time-indexed observations. Missing values in the selected window are
        dropped before fitting.
    start : str
        Inclusive start of the search window.
    end : str
        Inclusive end of the search window.
    min_segment : int, default=20
        Minimum segment size used to constrain candidate split positions.

    Returns
    -------
    tuple of (pandas.Timestamp, float, float)
        Timestamp of the first observation after the split, mean before the
        split, and mean after the split.

    Notes
    -----
    This is a descriptive single-change-point fit, not a significance test.
    It selects the candidate split with minimum combined within-segment
    squared error.
    """
    window = series.loc[start:end].dropna()
    values = window.to_numpy()
    best_sse, best_k = np.inf, None
    
    for k in range(min_segment, len(values) - min_segment):
        sse = (((values[:k] - values[:k].mean()) ** 2).sum()
               + ((values[k:] - values[k:].mean()) ** 2).sum())
        if sse < best_sse:
            best_sse, best_k = sse, k
            
    return window.index[best_k], values[:best_k].mean(), values[best_k:].mean()


# --------------------------------------------------------------------------
# Plot helper
# --------------------------------------------------------------------------

def plot_wind_rose(ax, table: pd.DataFrame, title: str = "") -> None:
    """Draw a stacked wind-rose chart on a polar Matplotlib axis.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        Polar axes, typically created with
        ``fig.add_subplot(..., projection="polar")``.
    table : pandas.DataFrame
        Sector-by-speed-bin values, typically produced by
        :func:`wind_rose_table`. The index should use ``COMPASS_16`` and the
        columns should be speed-bin labels.
    title : str, default=""
        Title to display above the chart.

    Returns
    -------
    None
        Adds bars and labels to ``ax`` in place.
    """
    import matplotlib.pyplot as plt
    
    angles = np.deg2rad(np.arange(16) * 22.5)
    width = np.deg2rad(22.5) * 0.9
    bottom = np.zeros(16)
    colors = plt.cm.viridis(np.linspace(0.15, 0.95, table.shape[1]))

    for color, label in zip(colors, table.columns):
        values = table[label].to_numpy()
        ax.bar(angles, values, width=width, bottom=bottom,
            color=color, label=f"{label} km/h", edgecolor="white", linewidth=0.3)
        bottom += values

    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_xticks(angles)
    ax.set_xticklabels(COMPASS_16, fontsize=8)
    ax.set_title(title, pad=14)
