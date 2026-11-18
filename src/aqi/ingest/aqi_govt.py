"""Fetch the latest CPCB station snapshot from data.gov.in.

This client is separate from the historical OpenCity and OpenAQ ingestion.
It requires ``DATA_GOV_API_KEY`` in ``.env`` and can be run with
``python -m aqi.ingest.aqi_govt``.
"""

import json
import os

import requests
from dotenv import load_dotenv

RESOURCE_ID = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"
BASE_URL = f"https://api.data.gov.in/resource/{RESOURCE_ID}"
STATION_NAME = "Ashok Vihar, Delhi - DPCC"


def fetch_station_data() -> list[dict[str, str]]:
    load_dotenv()
    api_key = os.getenv("DATA_GOV_API_KEY")
    if not api_key:
        raise RuntimeError("Set DATA_GOV_API_KEY in .env before running this script.")

    try:
        print(
            f"Requesting latest readings for {STATION_NAME} from data.gov.in...",
            flush=True,
        )
        response = requests.get(
            BASE_URL,
            params={
                "api-key": api_key,
                "format": "json",
                "limit": 100,
                "filters[station]": STATION_NAME,
            },
            headers={"Accept": "application/json"},
            timeout=(10, 20),
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        status = (
            f"HTTP {exc.response.status_code}"
            if exc.response is not None
            else type(exc).__name__
        )
        raise RuntimeError(f"Request to data.gov.in failed ({status}).") from None

    payload = response.json()
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("data.gov.in response did not contain a records list.")
    if not records:
        raise LookupError(f"No records found for station {STATION_NAME!r}.")

    return records


def main() -> None:
    records = fetch_station_data()
    print(f"Fetched {len(records)} records for {STATION_NAME}:")
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()