"""Tests for the OpenCity readers and the hourly time rules."""

import numpy as np
import pandas as pd
import pytest

from aqi.opencity import load_monthly_aqi_export, read_15min, to_hourly


def make_frame(hours=6):
    """15-minute frame: PM2.5 is 100 + hour index on the four rows of each hour,
    temperature counts up by one per row."""
    index = pd.date_range("2025-01-01 00:00", periods=4 * hours, freq="15min", name="time")
    pm25 = 100.0 + np.repeat(np.arange(hours), 4)
    return pd.DataFrame({"pm25": pm25, "at_c": np.arange(4 * hours, dtype=float)}, index=index)


def test_pm25_is_stamped_at_the_end_of_its_hour():
    hourly = to_hourly(make_frame())
    # the hour that started at 00:00 held 100; a forecast at 01:00 may use it
    assert hourly.loc["2025-01-01 01:00", "pm25"] == 100.0
    assert hourly.loc["2025-01-01 02:00", "pm25"] == 101.0
    # nothing is available before the first hour is complete
    assert hourly.index.min() == pd.Timestamp("2025-01-01 01:00")


def test_weather_is_the_mean_of_the_previous_hour_only():
    hourly = to_hourly(make_frame())
    # rows 00:15, 00:30, 00:45, 01:00 are temperatures 1, 2, 3, 4
    assert hourly.loc["2025-01-01 01:00", "at_c"] == pytest.approx(2.5)


def test_weather_needs_enough_rows():
    frame = make_frame()
    frame.loc["2025-01-01 02:30":"2025-01-01 03:00", "at_c"] = np.nan  # 3 of the 4 rows of (02:00, 03:00]
    hourly = to_hourly(frame)
    assert np.isnan(hourly.loc["2025-01-01 03:00", "at_c"])
    assert not np.isnan(hourly.loc["2025-01-01 04:00", "at_c"])


def test_pm_shift_moves_values_later():
    base = to_hourly(make_frame())
    shifted = to_hourly(make_frame(), pm_shift_hours=1)
    assert shifted.loc["2025-01-01 02:00", "pm25"] == base.loc["2025-01-01 01:00", "pm25"]


def test_no_value_is_stamped_before_its_hour_is_complete():
    frame = make_frame()
    hourly = to_hourly(frame)
    # PM2.5 stamped t came from the hour that started at t - 1h: its first row is
    # at t - 1h, so every value must equal 100 + (hours elapsed before t)
    for stamp, value in hourly["pm25"].dropna().items():
        hours_elapsed = int((stamp - frame.index.min()) / pd.Timedelta(hours=1))
        assert value == 100.0 + hours_elapsed - 1


def test_hourly_index_is_continuous_after_a_gap():
    frame = make_frame(hours=6)
    frame.loc["2025-01-01 02:00":"2025-01-01 02:45"] = np.nan
    hourly = to_hourly(frame)
    steps = hourly.index.to_series().diff().dropna()
    assert steps.eq(pd.Timedelta(hours=1)).all()


CSV_HEADER = ("Station ID,State,City,Station Name,Timestamp,PM2.5 (µg/m³),AT (°C),"
              "BP (mmHg),Xylene (µg/m³)")


def test_read_15min_drops_footer_keeps_ist_digits_and_fixes_pressure(tmp_path):
    rows = [
        "site_1,Delhi,Delhi,Test,2025-01-01T00:00:00.000000+0000,150.0,10.0,983.0,",
        "site_1,Delhi,Delhi,Test,2025-01-01T00:15:00.000000+0000,150.0,10.5,983.2,",
        "2025,,,,,,,,",  # footer row seen in the real files
    ]
    path = tmp_path / "recent.csv"
    path.write_text("\n".join([CSV_HEADER, *rows]) + "\n", encoding="utf-8")

    frame = read_15min(path)

    assert len(frame) == 2
    assert frame.index.tz is None
    assert frame.index[0] == pd.Timestamp("2025-01-01 00:00")          # digits kept, label ignored
    assert "xylene" not in " ".join(frame.columns).lower()              # empty column dropped
    assert "bp" not in frame.columns and "bp_hpa" in frame.columns
    assert frame["bp_hpa"].iloc[0] == pytest.approx(983.0)              # already hPa-sized


def test_read_15min_converts_real_mmhg(tmp_path):
    path = tmp_path / "anand.csv"
    path.write_text(
        "\n".join([
            CSV_HEADER,
            "site_2,Delhi,Delhi,Test,2024-01-01T00:00:00.000000+0000,150.0,11.5,742.0,",
            "site_2,Delhi,Delhi,Test,2024-01-01T00:15:00.000000+0000,150.0,11.5,742.0,",
        ]) + "\n", encoding="utf-8")
    frame = read_15min(path)
    assert frame["bp_hpa"].iloc[0] == pytest.approx(742.0 * 1.33322)


def test_read_15min_rejects_irregular_spacing(tmp_path):
    path = tmp_path / "gap.csv"
    path.write_text(
        "\n".join([
            CSV_HEADER,
            "s,Delhi,Delhi,T,2025-01-01T00:00:00.000000+0000,1,1,983,",
            "s,Delhi,Delhi,T,2025-01-01T00:30:00.000000+0000,1,1,983,",
        ]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_15min(path)


def test_monthly_matrix_parser(tmp_path):
    hours = ",".join(f"{h:02d}:00:00" for h in range(24))
    blank = ",".join([""] * 24)
    values = ",".join(["" if h < 2 else str(100 + h) for h in range(24)])
    text = "\n".join([
        "Year,2018",
        '"\n"' + "," * 24,
        f"February-2018,{hours}",
        f"1,{blank}",
        f"2,{values}",
    ]) + "\n"
    path = tmp_path / "legacy.csv"
    path.write_text(text, encoding="utf-8")

    series = load_monthly_aqi_export(path)

    assert series.index.min() == pd.Timestamp("2018-02-02 02:00")
    assert series.loc["2018-02-02 05:00"] == 105.0
    assert len(series) == 22
