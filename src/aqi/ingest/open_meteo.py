"""Open-Meteo archive ingest: raw hourly weather -> data/raw/."""

import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Open meteo archive API URL
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Path to the directory where raw dat
RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw"

# Variables to ingest by default
DEFAULT_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "rain",
    "wind_speed_10m",
    "wind_direction_10m",
    "surface_pressure",
]


# Retry strategy for HTTP requests
def _make_session() -> requests.Session:
    session = requests.Session()
    session.mount(
        "https://",
        HTTPAdapter(
            max_retries=Retry(
                total=5,
                backoff_factor=0.5,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET"],
            )
        ),
    )
    return session


# Function to fetch hourly data from Open-Meteo API
def fetch_hourly(lat: float, lon: float, start: str, end: str, variables: Sequence[str] = DEFAULT_VARIABLES, tz: str = "Asia/Kolkata", session: requests.Session | None = None,
    timeout: int = 60,
) -> pd.DataFrame:
    
    
    if session is None:
        session = _make_session()

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": variables,
        "start_date": start,
        "end_date": end,
        "timezone": tz,
    }
    
    response = session.get(ARCHIVE_URL, params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()

    if payload.get("error"):
        raise RuntimeError(f"Open-Meteo error: {payload.get('reason')}")

    df = pd.DataFrame(payload["hourly"])
    df["time"] = pd.to_datetime(df["time"])

    df.attrs = {
        "units": payload.get("hourly_units", {}),
        "grid_lat": payload.get("latitude"),
        "grid_lon": payload.get("longitude"),
        "elevation": payload.get("elevation"),
        "timezone": payload.get("timezone"),
        "requested": {"lat": lat, "lon": lon, "start": start, "end": end},
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    return df


def validate_hourly(
    df: pd.DataFrame,
    start: str,
    end: str,
    variables: Sequence[str],
) -> None:
    """Raise ValueError if hourly fields or timestamps are incomplete or invalid."""

    missing_columns = [column for column in ["time", *variables] if column not in df]
    if missing_columns:
        raise ValueError(f"Response is missing expected columns: {missing_columns}")

    empty_columns = [column for column in variables if df[column].isna().all()]
    if empty_columns:
        raise ValueError(f"Response has entirely empty columns: {empty_columns}")

    start_time = pd.Timestamp(start)
    end_time = pd.Timestamp(end)
    if end_time < start_time:
        raise ValueError(f"End date {end!r} is before start date {start!r}")

    expected_hours = (end_time - start_time).days * 24 + 24
    if len(df) != expected_hours:
        raise ValueError(f"Expected {expected_hours} hours of data, but got {len(df)}.")

    expected_last_time = end_time + pd.Timedelta(hours=23)
    times = pd.to_datetime(df["time"], errors="coerce")
    if times.isna().any():
        raise ValueError("Response contains missing or invalid timestamps")

    if times.duplicated().any():
        raise ValueError("Response contains duplicate timestamps")

    if not times.is_monotonic_increasing:
        raise ValueError("Response timestamps are not strictly increasing")

    if not times.diff().iloc[1:].eq(pd.Timedelta(hours=1)).all():
        raise ValueError("Response timestamps are not spaced exactly one hour apart")
    if times.iloc[0] != start_time:
        raise ValueError(f"Expected first timestamp {start_time}, got {times.iloc[0]}.")
    if times.iloc[-1] != expected_last_time:
        raise ValueError(
            f"Expected last timestamp {expected_last_time}, got {times.iloc[-1]}."
        )


def write_raw(df: pd.DataFrame, name: str = "open_meteo") -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RAW_DIR / f"{name}.parquet"
    df.to_parquet(output_path, index=False)
    metadata_path = RAW_DIR / f"{name}.meta.json"
    metadata_path.write_text(json.dumps(df.attrs, indent=2), encoding="utf-8")
    return output_path


def main() -> None:
    start, end = "2017-10-27", "2025-11-11"
    df = fetch_hourly(28.695, 77.181, start, end)
    validate_hourly(df, start, end, DEFAULT_VARIABLES)
    print(f"Wrote {len(df)} rows to {write_raw(df)}")


if __name__ == "__main__":
    main()
