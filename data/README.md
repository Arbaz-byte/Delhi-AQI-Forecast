# Data

Raw and interim data are **not committed** (see `.gitignore`). This file is the
data dictionary: one entry per source, filled in as each source is ingested and
audited.

| Source | What | Access | Terms checked | Status |
|---|---|---|---|---|
| CPCB station readings (via OpenCity / data.gov.in / OpenAQ) | Hourly pollutants per station | TBD | no | not started |
| Weather (Open-Meteo Archive API) | Hourly temperature, humidity, wind, rain, and pressure | Open-Meteo Archive API | YES | Ingested and audited (see below) |
| NASA FIRMS | Active-fire detections (Punjab/Haryana box) | Free MAP_KEY | no | not started |

## Weather: Open-Meteo Archive

Raw file: `raw/open_meteo.parquet`. Fetch metadata is stored alongside it in
`raw/open_meteo.meta.json`. Fetch code: `src/aqi/ingest/open_meteo.py`.
Full audit with figures: `notebooks/01_weather_audit.ipynb`.

Attribution: weather data by Open-Meteo.com (confirm the exact wording required
on their terms page before publishing).

### Coverage and location

- **Coverage:** 2003-01-01 00:00 through 2026-10-11 23:00, inclusive, in
  `Asia/Kolkata` local time (IST); 208,440 hourly rows (23.8 years). Every
  calendar year is complete except 2026 (77.8 %, record ends 11 October).
- **Requested location:** latitude 28.695, longitude 77.181 (Ashok Vihar,
  Delhi).
- **Returned grid point:** latitude 28.717047, longitude 77.15754, elevation
  219 m. These are the provider's grid-cell coordinates and elevation, not a
  ground station measurement at the requested coordinate.
- **Time representation:** the Parquet `time` column is timezone-naive; its
  values are local `Asia/Kolkata` time (verified, see audit step 5). India has
  no daylight saving, so `tz_localize("Asia/Kolkata")` is unambiguous.

### Variables and units

| Variable | Unit | Resolution | Notes |
|---|---|---|---|
| `temperature_2m` | °C | 0.1 | |
| `relative_humidity_2m` | % | 1 | 100 % occurs in 0.25 % of hours, 90 % of them in Dec–Feb (fog) |
| `rain` | mm per hour | 0.1 | Zero in 90.4 % of hours; handle as wet flag + amount |
| `wind_speed_10m` | km/h | 0.1 | **Level shift from ~2024-11-06, see below** |
| `wind_direction_10m` | degrees (from) | 1 | North is stored as **360**, never 0; stored as 270 for calm hours (placeholder) |
| `surface_pressure` | hPa | 0.1 | Falls to 965–970 hPa in May–Aug (heat low); not an error |

### Audit result (summary)

| Check | Result |
|---|---|
| Duplicates, ordering, 1-hour spacing, row count | pass |
| NaNs and sentinel codes (-999, -9999, 9999) | none |
| Range check | pass (pressure review range set to 960–1010 hPa) |
| Flat-lines | none for continuous variables (longest identical run 9 h) |
| Timezone | IST confirmed (temperature peaks 14:00 in all seasons) |
| Stability 2003–2024 | stable |
| **Stability 2024-11 onward** | **wind speed drops ~2.5 km/h (-0.85 sd); source change suspected** |

### Decisions

| ID | Decision |
|---|---|
| D1 | Keep the full 2003–2026 file as the raw archive; trim to the PM2.5 station overlap at join time. |
| D2 | Timestamps are IST; no shift. Make the zone explicit in the cleaning step; convert FIRMS (UTC) at its join. |
| D3 | No clipping or deletion; every flagged value was physical. |
| D4 | Never use wind direction in degrees: use u/v components, `direction % 360`, and u = v = 0 for calm hours. |
| D5 | Rain: wet flag + amount + rolling totals + hours since last rain; excluded from flat-line checks. |
| D6 | Wind speed has a break at ~2024-11-06; use the pre-shift period (to 2024-10-31) for descriptive wind statistics until O1 is resolved. |
| D7 | Four local seasons: Winter Dec–Feb, Pre-monsoon Mar–Jun, Monsoon Jul–Sep, Post-monsoon Oct–Nov (reused for PM2.5). |
| D8 | Compare seasons like for like: December belongs to the following season-year; drop incomplete seasons. |

### Open items

| ID | Item |
|---|---|
| O1 | Re-fetch with a pinned reanalysis model and check whether the Nov-2024 wind shift disappears. The planned final test season (autumn–winter 2025–26) lies entirely after the break. |
| O2 | Check whether `boundary_layer_height` and dew point can be requested from the archive. |
| O3 | Start logging weather-forecast snapshots now; archived forecasts cannot be recovered later. |
| O4 | Re-run the audit notebook after O1 and update D6. |

### Known limits

- This is gridded **reanalysis**, not a direct observation from a local weather
  station.
- The model grid resolution is approximately 10 km; local conditions may differ
  from the grid-cell estimate, and extremes are smoothed.
- Wind speed and direction are for **10 m** above the surface, not street or
  rooftop level.
- Visibility was unavailable (all-null in the archive response) and is not
  included in the saved dataset.
- Reanalysis is not a forecast: at forecast time *t* only information available
  at *t* may be used (see the leakage rule in the project proposal).

Treat audit findings as checks on this source and coverage, not as station-level
ground truth.

## Other source conventions

- Choose and document a canonical time zone when adding CPCB or FIRMS data;
  CPCB is local IST while some other sources use UTC.
- For any future gap filling, forward-fill only with a maximum gap length;
  never fill from the future.
- Flag potential sensor faults rather than deleting plausible real extremes.

## Layout

- `raw/` — files exactly as downloaded
- `interim/` — cleaned, aligned, Parquet
