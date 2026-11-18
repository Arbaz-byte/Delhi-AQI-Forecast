"""Behavioral tests for :mod:`aqi.audit`.

These tests use small synthetic pandas objects to check the audit helpers'
data-loading, validation, calendar, wind, and time-series diagnostic behavior
without relying on project datasets or network access.
"""

import numpy as np
import pandas as pd
import pytest

from aqi import audit


def test_load_hourly_sets_time_index_and_preserves_input_order(monkeypatch, tmp_path):
    source = pd.DataFrame(
        {
            "time": ["2025-01-01 01:00", "2025-01-01 00:00"],
            "temperature": [2.0, 1.0],
        }
    )
    monkeypatch.setattr(pd, "read_parquet", lambda _: source.copy())

    frame = audit.load_hourly(tmp_path / "weather.parquet")

    assert frame.index.name == "time"
    assert frame.index.tolist() == [
        pd.Timestamp("2025-01-01 01:00"),
        pd.Timestamp("2025-01-01 00:00"),
    ]
    assert frame["temperature"].tolist() == [2.0, 1.0]


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (pd.DataFrame(columns=["time"]), "No rows"),
        (pd.DataFrame({"temperature": [1.0]}), "no 'time' column"),
    ],
)
def test_load_hourly_rejects_empty_or_missing_time_column(
    monkeypatch, tmp_path, source, message
):
    monkeypatch.setattr(pd, "read_parquet", lambda _: source.copy())

    with pytest.raises(ValueError, match=message):
        audit.load_hourly(tmp_path / "weather.parquet")


def test_check_structure_returns_summary_for_complete_hourly_index():
    index = pd.date_range("2025-01-01", periods=3, freq="h", name="time")

    summary = audit.check_structure(pd.DataFrame(index=index))

    assert summary.loc["rows", "value"] == 3
    assert summary.loc["first", "value"] == index[0]
    assert summary.loc["last", "value"] == index[-1]
    assert summary.loc["timezone", "value"] == "naive (local IST)"
    assert summary.loc["duplicates", "value"] == 0
    assert summary.loc["gaps", "value"] == 0


@pytest.mark.parametrize(
    ("index", "error", "message"),
    [
        (pd.Index([0, 1]), TypeError, "DatetimeIndex"),
        (
            pd.DatetimeIndex(["2025-01-01", "2025-01-01"]),
            ValueError,
            "duplicate",
        ),
        (
            pd.DatetimeIndex(["2025-01-01 01:00", "2025-01-01 00:00"]),
            ValueError,
            "monotonic",
        ),
        (
            pd.DatetimeIndex(["2025-01-01 00:00", "2025-01-01 02:00"]),
            ValueError,
            "gaps",
        ),
    ],
)
def test_check_structure_rejects_invalid_indexes(index, error, message):
    with pytest.raises(error, match=message):
        audit.check_structure(pd.DataFrame(index=index))


def test_missing_summary_counts_nan_and_common_sentinels_only_for_numeric_data():
    frame = pd.DataFrame(
        {
            "pm25": [np.nan, -999, 12.0, 9999],
            "station": ["A", "B", "C", "D"],
        }
    )

    summary = audit.missing_summary(frame)

    assert summary.loc["pm25"].to_dict() == {"nan": 1, "sentinel": 2}
    assert "station" not in summary.index


def test_range_violations_counts_strictly_outside_bounds():
    frame = pd.DataFrame({"pm25": [0.0, 1.0, 5.0, 10.0, np.nan]})

    result = audit.range_violations(frame, {"pm25": (1.0, 5.0)})

    assert result.loc["pm25", "below"] == 1
    assert result.loc["pm25", "above"] == 1
    assert result.loc["pm25", "min"] == 0.0
    assert result.loc["pm25", "max"] == 10.0


def test_constant_runs_require_minimum_length_and_missing_values_break_runs():
    index = pd.date_range("2025-01-01", periods=8, freq="h")
    series = pd.Series([1, 1, 1, np.nan, 2, 2, 2, 2], index=index)

    runs = audit.constant_runs(series, min_hours=3)

    assert runs[["value", "hours"]].to_dict("records") == [
        {"value": 2.0, "hours": 4},
        {"value": 1.0, "hours": 3},
    ]
    assert runs.loc[1, "start"] == index[0]
    assert runs.loc[1, "end"] == index[2]


def test_add_calendar_assigns_seasons_and_december_to_following_season_year():
    index = pd.DatetimeIndex(
        ["2024-12-01", "2025-01-01", "2025-04-01", "2025-08-01", "2025-10-01"]
    )

    result = audit.add_calendar(pd.DataFrame(index=index))

    assert result["season"].astype(str).tolist() == [
        "Winter",
        "Winter",
        "Pre-monsoon",
        "Monsoon",
        "Post-monsoon",
    ]
    assert result["season_year"].tolist() == [2025, 2025, 2025, 2025, 2025]
    assert "month" not in pd.DataFrame(index=index).columns


@pytest.mark.parametrize("year, expected", [(2024, 8784), (2025, 8760)])
def test_expected_hours_in_year(year, expected):
    assert audit.expected_hours_in_year(year) == expected


def test_wind_components_follow_meteorological_direction_and_handle_calm():
    index = pd.RangeIndex(5)
    speed = pd.Series([1.0, 1.0, 1.0, 1.0, 0.0], index=index)
    direction = pd.Series([0.0, 90.0, 180.0, 270.0, 123.0], index=index)

    result = audit.wind_components(speed, direction)

    np.testing.assert_allclose(result["u"], [0.0, -1.0, 0.0, 1.0, 0.0], atol=1e-12)
    np.testing.assert_allclose(result["v"], [-1.0, 0.0, 1.0, 0.0, 0.0], atol=1e-12)


def test_wind_rose_wraps_north_bins_speed_and_can_normalise():
    speed = pd.Series([1.0, 5.0, 10.0, 20.0, 30.0, 0.0])
    direction = pd.Series([360.0, 90.0, 180.0, 270.0, 45.0, 0.0])

    counts = audit.wind_rose_table(speed, direction, normalise=False)
    percentages = audit.wind_rose_table(speed, direction)

    assert counts.loc["N", "0–<5"] == 1
    assert counts.loc["E", "5–<10"] == 1
    assert counts.loc["S", "10–<20"] == 1
    assert counts.loc["W", "20–<30"] == 1
    assert counts.loc["NE", "30+"] == 1
    assert counts.to_numpy().sum() == 5
    assert percentages.to_numpy().sum() == pytest.approx(100.0)


def test_deseasonalise_removes_month_hour_means():
    index = pd.date_range("2025-01-01", periods=48, freq="h")
    values = np.tile(np.arange(24, dtype=float), 2) + np.repeat([0.0, 10.0], 24)

    result = audit.deseasonalise(pd.Series(values, index=index))

    np.testing.assert_allclose(result.iloc[:24], -5.0)
    np.testing.assert_allclose(result.iloc[24:], 5.0)


def test_autocorrelation_returns_values_at_requested_lags():
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])

    result = audit.autocorrelation(series, [1, 2])

    assert result.index.tolist() == [1, 2]
    assert result.tolist() == pytest.approx([1.0, 1.0])


def test_daily_anomaly_uses_baseline_without_absorbing_later_level():
    index = pd.date_range("2024-01-01", "2026-01-03 23:00", freq="h")
    values = np.where(index.year == 2026, 20.0, 10.0)

    result = audit.daily_anomaly(pd.Series(values, index=index), "2025-01-03")

    assert result.loc["2026-01-01":"2026-01-03"].tolist() == [10.0, 10.0, 10.0]


def test_find_level_shift_locates_synthetic_mean_change():
    index = pd.date_range("2025-01-01", periods=60, freq="h")
    series = pd.Series([10.0] * 30 + [20.0] * 30, index=index)

    change_time, before, after = audit.find_level_shift(
        series, str(index[0]), str(index[-1]), min_segment=5
    )

    assert change_time == index[30]
    assert before == pytest.approx(10.0)
    assert after == pytest.approx(20.0)
