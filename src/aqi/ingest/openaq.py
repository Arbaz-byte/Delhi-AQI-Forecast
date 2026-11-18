"""Fetch hourly OpenAQ pollutant readings near Ashok Vihar, Delhi.

Set ``OPEN_AQ_KEY`` (or ``OPENAQ_API_KEY``) in the repository's ``.env`` file,
then run: ``python -m aqi.ingest.openaq``.
Edit ``START_DATE`` and ``END_DATE`` below to set the inclusive local date range.
Results are fetched and saved one calendar year at a time.
Only the locations in ``LOCATION_IDS`` have their hourly data downloaded; the
other nearby locations are still listed in the metadata sidecar.

This writes raw hourly concentrations, not a CPCB AQI: AQI calculation
requires pollutant-specific averaging windows and valid coverage. Each row
also includes the sensor's earliest and latest available observation times.
Fetch and location/sensor metadata are saved beside each Parquet file as
``*.meta.json``.
"""

from __future__ import annotations

import json
import os
import time as time_module
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API_URL = "https://api.openaq.org/v3"
ASHOK_VIHAR_LAT = 28.695
ASHOK_VIHAR_LON = 77.181
SEARCH_RADIUS_METERS = 5_000
PAGE_SIZE = 1_000
MAX_PAGES = 100

# Edit these dates to choose the inclusive Ashok Vihar local-time range.
# The CPCB sensors at location 8917 report from 2025-02-19 (see the metadata).
START_DATE = "2025-02-01"
END_DATE = date.today().isoformat()

# OpenAQ location ids to download. 8917 = "Ashok Vihar, Delhi - DPCC" (CPCB feed).
# Set to None to download every location returned by the radius search.
LOCATION_IDS: tuple[int, ...] | None = (8917,)

# The free tier allows 60 requests/minute; pause between calls to stay under it.
REQUEST_PAUSE_SECONDS = 1.1

AQI_PARAMETERS = {
    "pm25",
    "pm10",
    "no2",
    "so2",
    "co",
    "o3",
    "nh3",
    "pb",
}

PARAMETER_ALIASES = {
    "pm2.5": "pm25",
    "pm2_5": "pm25",
    "ozone": "o3",
    "lead": "pb",
}
RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "OpenAq"
OUTPUT_PATH = RAW_DIR / "ashok_vihar_hourly.parquet"
LOCAL_TIMEZONE = ZoneInfo("Asia/Kolkata")


def _make_session() -> requests.Session:
    """Create a session that backs off on OpenAQ rate limits and transient errors."""
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def _get_results(
    session: requests.Session,
    endpoint: str,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    """Fetch all pages from an OpenAQ endpoint."""
    results: list[dict[str, Any]] = []
    page = 1
    while True:
        if endpoint.endswith("/hours"):
            print(f"  Requesting {endpoint}, page {page}")
        try:
            response = session.get(
                f"{API_URL}/{endpoint}",
                params={**params, "page": page, "limit": PAGE_SIZE},
                timeout=(10, 30),
            )
        except requests.exceptions.RetryError as exc:
            raise RuntimeError(
                f"OpenAQ request for {endpoint!r} failed after retries. "
                "The API may still be rate-limiting requests; wait and try again."
            ) from exc
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            wait_message = (
                f" Retry after {retry_after} seconds."
                if retry_after
                else " Wait briefly before trying again."
            )
            raise RuntimeError(f"OpenAQ rate limit reached.{wait_message}")
        response.raise_for_status()
        time_module.sleep(REQUEST_PAUSE_SECONDS)
        payload = response.json()
        page_results = payload.get("results")
        if not isinstance(page_results, list):
            raise TypeError(f"OpenAQ response for {endpoint!r} has no results list.")
        results.extend(page_results)
        if endpoint.endswith("/hours"):
            print(f"  {endpoint}: page {page}, received {len(page_results)} rows")
        if len(page_results) < PAGE_SIZE:
            return results
        if page >= MAX_PAGES:
            raise RuntimeError(
                f"Stopped after {MAX_PAGES} pages for {endpoint!r}; "
                "narrow the configured date range."
            )
        page += 1


def _parameter_name(sensor: dict[str, Any]) -> str | None:
    parameter = sensor.get("parameter")
    if not isinstance(parameter, dict):
        return None
    name = str(parameter.get("name", "")).strip().lower()
    name = PARAMETER_ALIASES.get(name, name)
    return name if name in AQI_PARAMETERS else None


def fetch_hourly(
    radius_meters: int = SEARCH_RADIUS_METERS,
    session: requests.Session | None = None,
    start_date: str = START_DATE,
    end_date: str = END_DATE,
    location_ids: tuple[int, ...] | None = LOCATION_IDS,
) -> pd.DataFrame:
    """Return hourly readings for an inclusive range of Ashok Vihar local dates.

    Only ``location_ids`` are downloaded (``None`` means all locations found).

    Sensor units are retained as reported by OpenAQ; gas readings may need
    unit conversion before applying CPCB breakpoints.
    """
    try:
        first_day = date.fromisoformat(start_date)
        last_day = date.fromisoformat(end_date)
    except ValueError as exc:
        raise ValueError("Dates must use YYYY-MM-DD format.") from exc
    if last_day < first_day:
        raise ValueError("end_date must be on or after start_date.")
    if radius_meters <= 0:
        raise ValueError("radius_meters must be greater than zero.")
    start = datetime.combine(first_day, time.min, tzinfo=LOCAL_TIMEZONE).astimezone(
        timezone.utc
    )
    # The hours endpoint appears to filter on each period's END, so a window that
    # stops at 23:59:59 drops the final 23:00-24:00 hour. End at the next local
    # midnight instead (verify: the last row should now start at 23:00).
    end = datetime.combine(
        last_day + timedelta(days=1), time.min, tzinfo=LOCAL_TIMEZONE
    ).astimezone(timezone.utc)

    load_dotenv()
    api_key = os.getenv("OPEN_AQ_KEY") or os.getenv("OPENAQ_API_KEY")
    if not api_key:
        raise RuntimeError("Set OPEN_AQ_KEY (or OPENAQ_API_KEY) in the repository's .env file.")

    owns_session = session is None
    if session is None:
        session = _make_session()
    session.headers.update({"X-API-Key": api_key, "Accept": "application/json"})

    query = {
        "coordinates": f"{ASHOK_VIHAR_LAT},{ASHOK_VIHAR_LON}",
        "radius": radius_meters,
        "country": "IN",
        "isMobile": "false",
    }

    try:
        locations = _get_results(session, "locations", query)
        if not locations:
            raise LookupError(
                "OpenAQ returned no monitoring locations within "
                f"{radius_meters} m of Ashok Vihar, Delhi."
            )

        rows: list[dict[str, Any]] = []
        location_metadata: list[dict[str, Any]] = []
        sensor_metadata_records: list[dict[str, Any]] = []
        seen_locations: set[Any] = set()
        seen_sensors: set[Any] = set()
        for location in locations:
            sensors = location.get("sensors", [])
            if not isinstance(sensors, list):
                continue
            coordinates = location.get("coordinates") or {}
            location_id = location.get("id")
            if location_id not in seen_locations:
                location_metadata.append(
                    {key: value for key, value in location.items() if key != "sensors"}
                )
                seen_locations.add(location_id)
            for sensor in sensors:
                parameter = _parameter_name(sensor)
                if parameter is None:
                    continue
                sensor_id = sensor.get("id")
                if sensor_id is None:
                    continue

                sensor_metadata = sensor
                first_available = sensor_metadata.get("datetimeFirst")
                last_available = sensor_metadata.get("datetimeLast")
                if (
                    not isinstance(first_available, dict)
                    or not first_available.get("utc")
                    or not isinstance(last_available, dict)
                    or not last_available.get("utc")
                ):
                    details = _get_results(session, f"sensors/{sensor_id}", {})
                    if details:
                        sensor_metadata = {**sensor, **details[0]}
                first_available = sensor_metadata.get("datetimeFirst") or {}
                last_available = sensor_metadata.get("datetimeLast") or {}
                if sensor_id not in seen_sensors:
                    sensor_metadata_records.append(
                        {
                            "location_id": location_id,
                            "location_name": location.get("name"),
                            "sensor": sensor_metadata,
                        }
                    )
                    seen_sensors.add(sensor_id)

                if location_ids is not None and location_id not in location_ids:
                    continue  # metadata is kept, hours are not downloaded

                observations = _get_results(
                    session,
                    f"sensors/{sensor_id}/hours",
                    {
                        "datetime_from": start.isoformat().replace("+00:00", "Z"),
                        "datetime_to": end.isoformat().replace("+00:00", "Z"),
                    },
                )
                for observation in observations:
                    period = observation.get("period") or {}
                    datetime_from = period.get("datetimeFrom") or {}
                    datetime_to = period.get("datetimeTo") or {}
                    rows.append(
                        {
                            "timestamp_utc": datetime_from.get("utc"),
                            "timestamp_local": datetime_from.get("local"),
                            "period_end_utc": datetime_to.get("utc"),
                            "parameter": parameter,
                            "value": observation.get("value"),
                            "unit": (observation.get("parameter") or {}).get(
                                "units",
                                (sensor_metadata.get("parameter") or {}).get("units"),
                            ),
                            "sensor_id": sensor_id,
                            "sensor_first_utc": first_available.get("utc"),
                            "sensor_first_local": first_available.get("local"),
                            "sensor_last_utc": last_available.get("utc"),
                            "sensor_last_local": last_available.get("local"),
                            "location_id": location.get("id"),
                            "location_name": location.get("name"),
                            "latitude": coordinates.get("latitude"),
                            "longitude": coordinates.get("longitude"),
                        }
                    )

        if not rows:
            raise LookupError(
                "No hourly AQI-pollutant observations were returned near "
                "Ashok Vihar for the requested period."
            )

        frame = pd.DataFrame(rows)
        frame["timestamp_utc"] = pd.to_datetime(
            frame["timestamp_utc"], utc=True, errors="coerce"
        )
        frame["period_end_utc"] = pd.to_datetime(
            frame["period_end_utc"], utc=True, errors="coerce"
        )
        for column in ("sensor_first_utc", "sensor_last_utc"):
            frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
        frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
        frame = frame.dropna(subset=["timestamp_utc", "value"])
        frame = frame.sort_values(
            ["timestamp_utc", "location_name", "parameter"]
        ).reset_index(drop=True)
        units_by_parameter = {
            parameter: sorted(
                frame.loc[frame["parameter"] == parameter, "unit"]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )
            for parameter in sorted(frame["parameter"].unique())
        }
        frame.attrs.update(
            {
                "source": "OpenAQ API v3",
                "attribution": "Data provided by OpenAQ and its listed data providers.",
                "location": "Ashok Vihar, Delhi",
                "downloaded_location_ids": (
                    sorted(location_ids) if location_ids is not None else "all"
                ),
                "requested_location": {
                    "latitude": ASHOK_VIHAR_LAT,
                    "longitude": ASHOK_VIHAR_LON,
                    "radius_meters": radius_meters,
                },
                "requested_local_dates": {
                    "start": first_day.isoformat(),
                    "end": last_day.isoformat(),
                    "timezone": str(LOCAL_TIMEZONE),
                },
                "window_start_utc": start.isoformat(),
                "window_end_utc": end.isoformat(),  # exclusive local midnight after end_date
                "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                "units_by_parameter": units_by_parameter,
                "locations": location_metadata,
                "sensors": sensor_metadata_records,
                "pollutants_not_found": sorted(
                    AQI_PARAMETERS - set(frame["parameter"].unique())
                ),
                "note": (
                    "Raw hourly values and source units; not a calculated CPCB AQI."
                ),
            }
        )
        return frame
    finally:
        if owns_session:
            session.close()


def write_raw(frame: pd.DataFrame, output_path: Path = OUTPUT_PATH) -> Path:
    """Write readings (Parquet) and a metadata sidecar (``*.meta.json``)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output_path, index=False)
    metadata_path = output_path.with_suffix(".meta.json")
    metadata_path.write_text(
        json.dumps(frame.attrs, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_path


def main() -> None:
    first_day = date.fromisoformat(START_DATE)
    last_day = date.fromisoformat(END_DATE)
    if last_day < first_day:
        raise ValueError("END_DATE must be on or after START_DATE.")

    for year in range(first_day.year, last_day.year + 1):
        year_start = max(first_day, date(year, 1, 1))
        year_end = min(last_day, date(year, 12, 31))
        print(f"Fetching {year_start} through {year_end} (Ashok Vihar local dates)")
        try:
            frame = fetch_hourly(
                start_date=year_start.isoformat(),
                end_date=year_end.isoformat(),
            )
        except LookupError as exc:
            print(f"No readings for {year}: {exc}")
            continue

        output_path = RAW_DIR / f"ashok_vihar_hourly_{year}.parquet"
        path = write_raw(frame, output_path)
        print(f"Saved {len(frame)} hourly readings to {path}")
        print(f"Saved fetch metadata to {path.with_suffix('.meta.json')}")
        available = ", ".join(sorted(frame["parameter"].unique()))
        missing = ", ".join(frame.attrs["pollutants_not_found"]) or "none"
        print(f"Pollutants found: {available}; not found: {missing}")
        coverage = (
            frame[["parameter", "sensor_id", "sensor_first_local", "sensor_last_local"]]
            .drop_duplicates()
            .sort_values(["parameter", "sensor_id"])
        )
        for row in coverage.itertuples(index=False):
            print(
                f"{row.parameter} sensor {row.sensor_id} available: "
                f"{row.sensor_first_local or 'unknown'} to "
                f"{row.sensor_last_local or 'unknown'}"
            )

    print("Values retain OpenAQ's reported units; convert/validate before AQI.")


if __name__ == "__main__":
    main()
