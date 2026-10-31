"""
Reusable data-audit helpers for hourly time-series sources.

Used first for the Open-Meteo weather audit (notebooks/01_weather_audit.ipynb)
and meant to be reused for station PM2.5 and fire data.


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


# Load hourly data from a given path
def load_hourly(path: str | Path) -> pd.DataFrame:
    
    """
    Read a raw parquet file and index it by its `time` column.
    The index is deliberately not sorted here: sorting first could hide an
    ordering problem that `check_structure` should catch.
    """
    df = pd.read_parquet(path)
    
    if df.empty:
        raise ValueError(f"No rows found in {path}")
    if "time" not in df.columns:
        raise ValueError("Parquet data has no 'time' column")
    
    df.index = pd.DatetimeIndex(pd.to_datetime(df.pop("time")), name="time")
    return df


# Structure Audit function to ensure the data is in a clean, complete hourly series
def check_structure(df: pd.DataFrame) -> pd.DataFrame:
    """
    Raise ValueError if the index is not a clean, complete hourly series.\
    Returns a one-row summary table when everything passes.
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


# Check For Missing Values 
def missing_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-column count of NaNs and common sentinel values.
    
    """
    
    # Outliers Values 
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
    
    """ Count values outside broad review ranges (None = unbounded). """
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
    """
    Runs of >= `min_hours` identical consecutive values.
    A missing value breaks a run; it is never counted as a repeat.
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
    """
    Return a copy with month, hour, season and season_year columns.
    `season_year` assigns December to the *following* year so that one winter
    (Dec, Jan, Feb) is a single group instead of being split across years.
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
    return (366 if pd.Timestamp(year=year, month=1, day=1).is_leap_year else 365) * 24


# --------------------------------------------------------------------------
# Wind
# --------------------------------------------------------------------------

def wind_components(speed: pd.Series, direction: pd.Series) -> pd.DataFrame:
    """
    Meteorological wind to u/v components (u east, v north).
    Direction is where the wind comes FROM, hence the minus signs. Calm hours
    (speed == 0) get u = v = 0 whatever the stored direction is.
    """
    
    """  
    [ u = -S\sin(\theta), \qquad v = -S\cos(\theta) ] 
    
    where, 
    1. (S) is wind speed.
    2. (\theta) is wind direction in radians. The input direction is in degrees, so np.deg2rad(direction) converts it before applying sine and cosine.
    3. u is the east–west component: positive means eastward, negative means westward.
    4. v is the north–south component: positive means northward, negative means southward
        
    """
    
    rad = np.deg2rad(direction)
    
    return pd.DataFrame(
        {"u": -speed * np.sin(rad), "v": -speed * np.cos(rad)},
        index=speed.index,
    )


def wind_rose_table( speed: pd.Series, direction: pd.Series, normalise: bool = True ) -> pd.DataFrame:
    """
    16-sector x speed-bin table for a wind rose. Calm hours are excluded.

    Direction is wrapped with `% 360`, so 360 (north in this dataset) is kept.
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
    
    """Remove the mean annual+diurnal cycle (mean by month x hour)."""
    
    key = [series.index.month, series.index.hour]
    return series - series.groupby(key).transform("mean")


def autocorrelation(series: pd.Series, lags: Sequence[int]) -> pd.Series:
    """Pearson autocorrelation at the given hourly lags."""
    
    return pd.Series({lag: series.autocorr(lag=lag) for lag in lags})


# --------------------------------------------------------------------------
# Stability / level shifts
# --------------------------------------------------------------------------

def daily_anomaly(series: pd.Series, baseline_end: str) -> pd.Series:
    """
    Daily mean minus a smoothed day-of-year climatology.
    The climatology is fitted on data up to `baseline_end` only, so later
    shifts show up as anomalies instead of being absorbed into the baseline.
    """
    
    daily = series.resample("D").mean()
    base = daily.loc[:baseline_end]
    clim = (
        base.groupby(base.index.dayofyear).mean()
        .rolling(15, center=True, min_periods=1).mean()
    )
    return daily - clim.reindex(daily.index.dayofyear).to_numpy()


def find_level_shift( series: pd.Series, start: str, end: str, min_segment: int = 20 ) -> tuple[pd.Timestamp, float, float]:
    """
    Single least-squares change point of the mean inside [start, end].
    Returns (change_date, mean_before, mean_after). A descriptive tool, not a
    significance test: it always returns *some* split.
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
    """
    Stacked polar bars from `wind_rose_table` (values are % of hours).
    `ax` must be a polar axis: `fig.add_subplot(..., projection="polar")`.
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
