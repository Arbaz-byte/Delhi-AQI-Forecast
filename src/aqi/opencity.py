"""Readers for OpenCity's differently shaped station exports.

* ``load_monthly_aqi_export``: the 2017-2023 month x day x hour matrix.
* ``read_15min``: the 2024-25 tidy 15-minute file (pollutants + on-site weather).
* ``to_hourly``: 15-minute frame to an hourly frame with explicit time rules.
"""

from __future__ import annotations

import calendar
import csv
import re
from pathlib import Path

import pandas as pd

_MONTH_HEADER = re.compile(r"([A-Za-z]+)-(\d{4})")


def load_monthly_aqi_export(path: str | Path) -> pd.Series:
    """Unpivot OpenCity's 2017–2023 month-by-day-by-hour AQI export.

    The export contains a year row, a month row with 24 hourly labels, then
    daily rows. It also contains quoted newline-only rows, which are ignored.
    Blank observation cells are omitted; their missing timestamps remain
    visible as gaps in the returned hourly index.
    """
    timestamps: list[pd.Timestamp] = []
    values: list[float] = []
    current_year: int | None = None
    current_month: int | None = None
    month_numbers = {name.lower(): number for number, name in enumerate(calendar.month_name) if name}

    with Path(path).open(encoding="utf-8-sig", newline="") as csv_file:
        for row_number, row in enumerate(csv.reader(csv_file), start=1):
            cells = [cell.strip() for cell in row]
            if not cells or all(cell in {"", "\n", "\r"} for cell in cells):
                continue

            if cells[0] == "Year":
                if len(cells) != 2 or not cells[1].isdigit():
                    raise ValueError(f"Invalid year header on CSV row {row_number}.")
                current_year = int(cells[1])
                current_month = None
                continue

            month_match = _MONTH_HEADER.fullmatch(cells[0])
            if month_match:
                month_name, year_text = month_match.groups()
                month_number = month_numbers.get(month_name.lower())
                if month_number is None:
                    raise ValueError(f"Unknown month on CSV row {row_number}: {month_name!r}.")
                if len(cells) != 25:
                    raise ValueError(f"Expected 24 hourly labels on CSV row {row_number}.")
                expected_hours = [f"{hour:02d}:00:00" for hour in range(24)]
                if cells[1:] != expected_hours:
                    raise ValueError(f"Unexpected hourly labels on CSV row {row_number}.")
                current_year = int(year_text)
                current_month = month_number
                continue

            if current_year is None or current_month is None:
                raise ValueError(f"Observation row before a month header on CSV row {row_number}.")
            if len(cells) != 25 or not cells[0].isdigit():
                raise ValueError(f"Invalid daily row on CSV row {row_number}.")

            day = int(cells[0])
            if not 1 <= day <= calendar.monthrange(current_year, current_month)[1]:
                raise ValueError(f"Invalid day on CSV row {row_number}: {day}.")

            for hour, cell in enumerate(cells[1:]):
                if not cell:
                    continue
                try:
                    value = float(cell)
                except ValueError as exc:
                    raise ValueError(
                        f"Non-numeric observation on CSV row {row_number}: {cell!r}."
                    ) from exc
                timestamp = pd.Timestamp(
                    year=current_year, month=current_month, day=day, hour=hour
                )
                timestamps.append(timestamp)
                values.append(value)

    if not values:
        raise ValueError(f"No numeric observations found in {path}.")

    return pd.Series(
        values,
        index=pd.DatetimeIndex(timestamps, name="time"),
        name="AQI_candidate",
    )


# ---------------------------------------------------------------------------
# 2024-25 tidy 15-minute files
# ---------------------------------------------------------------------------

COLUMN_NAMES = {
    "PM2.5 (µg/m³)": "pm25",
    "PM10 (µg/m³)": "pm10",
    "NO (µg/m³)": "no",
    "NO2 (µg/m³)": "no2",
    "NOx (ppb)": "nox",
    "NH3 (µg/m³)": "nh3",
    "SO2 (µg/m³)": "so2",
    "CO (mg/m³)": "co",
    "Ozone (µg/m³)": "o3",
    "Benzene (µg/m³)": "benzene",
    "Toluene (µg/m³)": "toluene",
    "AT (°C)": "at_c",
    "RH (%)": "rh_pct",
    "WS (m/s)": "ws_ms",
    "WD (deg)": "wd_deg",
    "RF (mm)": "rf_mm",
    "TOT-RF (mm)": "tot_rf_mm",
    "SR (W/mt2)": "sr_wm2",
    "BP (mmHg)": "bp",
}
PM_COLUMNS = ["pm25", "pm10"]
HPA_PER_MMHG = 1.33322


def read_15min(path: str | Path) -> pd.DataFrame:
    """Read an OpenCity 2024-25 file into a tidy 15-minute frame.

    * Rows without a parsable timestamp (the footer row) are dropped.
    * The ``+0000`` suffix is **not** trusted: solar radiation peaks at 12:00 on
      the stored clock, so the stored digits are Indian Standard Time. The index
      keeps those digits as a naive timestamp (``time``, IST wall clock).
    * Columns get short names; columns that are entirely empty are dropped.
    * The pressure column is called ``bp`` and converted to ``bp_hpa``: the label
      says mmHg, but some stations report hPa-sized values (median above 900).
    * The spacing must be exactly 15 minutes, otherwise ValueError.
    """
    raw = pd.read_csv(path, low_memory=False)
    stamp = pd.to_datetime(raw["Timestamp"], utc=True, errors="coerce")
    keep = stamp.notna()
    frame = raw.loc[keep].copy()
    frame.index = pd.DatetimeIndex(stamp[keep].dt.tz_localize(None), name="time")

    meta_columns = [c for c in ("Station ID", "Station Name") if c in frame.columns]
    station = frame[meta_columns].drop_duplicates() if meta_columns else None
    frame = frame.rename(columns=COLUMN_NAMES)
    frame = frame[[c for c in COLUMN_NAMES.values() if c in frame.columns]]
    frame = frame.apply(pd.to_numeric, errors="coerce").dropna(axis=1, how="all")

    if "bp" in frame.columns:
        median = frame["bp"].median()
        frame["bp_hpa"] = frame["bp"] if median > 900 else frame["bp"] * HPA_PER_MMHG
        frame = frame.drop(columns="bp")

    if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
        raise ValueError("Timestamps are not strictly increasing.")
    steps = frame.index.to_series().diff().dropna()
    if not steps.eq(pd.Timedelta(minutes=15)).all():
        raise ValueError(f"Spacing is not 15 minutes: {steps.value_counts().head().to_dict()}")

    if station is not None:
        frame.attrs["station"] = station.astype(str).to_dict("records")
    frame.attrs["clock"] = "stored digits treated as IST wall time"
    return frame


def to_hourly(
    frame: pd.DataFrame, pm_shift_hours: int = 0, min_rows: int = 3
) -> pd.DataFrame:
    """15-minute frame to hourly, indexed by the **end** of each hour (as-of time).

    A row stamped ``t`` may be used by a forecast issued at ``t`` and later, so
    every column is stamped with the moment its hour is complete:

    * ``pm25``, ``pm10``: the file repeats one hourly value on four rows. The value
      for the hour that *starts* at H is the first non-null row in [H, H+1h),
      stamped H+1h. If the overlap check against OpenAQ finds a constant offset,
      pass it as ``pm_shift_hours`` (positive moves values later).
    * everything else (weather, gases): mean of the previous hour, i.e. rows in
      (t-1h, t], stamped t, and NaN unless at least ``min_rows`` of the 4 rows exist.
    """
    pm_cols = [c for c in PM_COLUMNS if c in frame.columns]
    other_cols = [c for c in frame.columns if c not in pm_cols]

    pieces = []
    if pm_cols:
        pm = frame[pm_cols].resample("h").first()          # label = hour start
        pm.index = pm.index + pd.Timedelta(hours=1 + pm_shift_hours)
        pieces.append(pm)
    if other_cols:
        grouped = frame[other_cols].resample("h", closed="right", label="right")
        mean = grouped.mean()
        pieces.append(mean.where(grouped.count() >= min_rows))

    hourly = pd.concat(pieces, axis=1, sort=True)
    # Trim all-NaN rows at the two ends (the first bin holds a single row). Gaps in
    # the middle stay as NaN rows so the hourly index remains continuous.
    valid = hourly.dropna(how="all").index
    hourly = hourly.loc[valid.min():valid.max()]
    hourly.index.name = "time_end"
    hourly.attrs.update(frame.attrs)
    return hourly
