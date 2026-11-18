# Data

Raw and interim data are **not committed** (see `.gitignore`). This file is the
data dictionary: one entry per source, filled in as each source is ingested and
audited.

| Source | What | Access | Terms checked | Status |
|---|---|---|---|---|
| CPCB station readings (via OpenCity / data.gov.in / OpenAQ) | Ashok Vihar PM2.5 and related pollutants | OpenCity CSV + OpenAQ API export | no | 2024–25 OpenCity and Feb 2025–Nov 2026 OpenAQ ingested; 2025 overlap is available, but the source seam and clock convention remain unvalidated; legacy AQI-like file excluded from the PM2.5 target |
| Weather (Open-Meteo Archive API) | Hourly temperature, humidity, wind, rain, and pressure | Open-Meteo Archive API | YES | Ingested and audited (see below) |
| NASA FIRMS | Active-fire detections (Punjab/Haryana box) | Free MAP_KEY | no | not started |

## Weather: Open-Meteo Archive

Raw file: `raw/open_meteo/open_meteo.parquet`. Fetch metadata is stored
alongside it in `raw/open_meteo/open_meteo.meta.json`. Fetch code:
`src/aqi/ingest/open_meteo.py`.
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

## OpenCity: Ashok Vihar (first-pass audit)

Raw files:

- `raw/OpenCity/del-ashok-vihar-2017_2023.csv`
- `raw/OpenCity/del-ashok-vihar-dpcc-2024-25 .csv`

Audit notebook: `notebooks/02_opencity_audit.ipynb`. The legacy matrix reader is
`src/aqi/opencity.py`.

### Coverage and identity

| File | Parsed observations | First / last timestamp on stored clock | Finding |
|---|---:|---|---|
| 2017–2023 matrix | 46,809 hourly values | 2018-02-01 09:00 / 2023-12-31 23:00 | The file has a 2017 header but no numeric 2017 observations. There are 5,022 missing hourly slots inside the observed span. |
| 2024–2025 station export | 70,176 valid 15-minute rows | 2024-01-01 00:00 / 2025-12-31 23:45 | `site_1420`, Ashok Vihar, Delhi - DPCC; complete quarter-hour timestamp grid. One extra footer-like row has no timestamp. |

The older filename says Ashok Vihar, but its observation matrix contains no
station ID or name. Therefore station continuity with the newer `site_1420`
file is plausible, not verified from both files' contents.

### Measurement and time decisions

- The older values range from **1 to 500**, including 1,148 values exactly at
  500. They look AQI-like, but the file has no variable/unit label; do **not**
  treat them as PM2.5 concentrations without source metadata.
- The newer file labels PM2.5 as **µg/m³**; its values range from 1 to 965 and
  1,582 of the valid-timestamp PM2.5 records are null. No common sentinel
  values were found in numeric measurements. Xylene, O Xylene, Eth-Benzene,
  MP-Xylene, and VWS are entirely null.
- New-file timestamps carry a `+0000` suffix, but the mean solar-radiation
  profile peaks at 12:00 on the stored clock and at 18:00 after literal
  UTC-to-IST conversion. Treat this as an unresolved timezone-label/clock
  conflict; do not shift timestamps until the export convention is confirmed.
- PM2.5 changes on the stored clock mostly at :00 (12,764 transitions) and
  also at :45 (3,011), with some at :15 and :30. There is no single established
  update minute or availability-time rule.
- Do not concatenate the older AQI-like series with the newer PM2.5
  concentration series. Confirm the old measure, station continuity, and time
  convention first. The OpenAQ audit follows below; the source seam remains
  unvalidated.

## OpenAQ: Ashok Vihar (2025–2026)

Raw files:

- `raw/OpenAq/ashok_vihar_hourly_2025.parquet` — hourly observations requested for 2025-02-01 through 2025-12-31.
- `raw/OpenAq/ashok_vihar_hourly_2025.meta.json` — request, location, sensor, and unit metadata.
- `raw/OpenAq/ashok_vihar_hourly_2026.parquet` — hourly observations requested for 2026-01-01 through 2026-11-16.
- `raw/OpenAq/ashok_vihar_hourly_2026.meta.json` — request, location, sensor, and unit metadata.

Both pulls were made on **2026-11-16** within 5 km of Ashok Vihar, using local
dates in `Asia/Kolkata`. `LOCATION_IDS=(8917,)` filtered the observation files
to **location 8917**, Ashok Vihar, Delhi - DPCC (CPCB). The sidecars retain
metadata for nearby locations and sensors; do not interpret that inventory as
additional observations in the Parquet files.

### Coverage and variables

| File | Total rows | PM2.5 rows | PM2.5 first / last (IST) | Expected hours within observed span | Missing | Coverage | Longest missing run |
|---|---:|---:|---|---:|---:|---:|---:|
| 2025 | 42,622 | 7,149 | 2025-02-19 01:00 / 2025-12-31 23:00 | 7,583 | 434 | 94.28% | 61 h |
| 2026 | 40,594 | 6,682 | 2026-01-01 00:00 / 2026-11-16 10:00 | 7,667 | 985 | 87.15% | 242 h |

Coverage is calculated only between each file's first and last PM2.5 timestamp;
it excludes dates outside that observed span. The 2025 request starts on
Feb 1, but the first PM2.5 observation is Feb 19. These are sparse hourly
series, not complete date ranges; missing hours are absent rows rather than
null-valued rows. The longest gaps above are counts of consecutive missing
hourly timestamps.

| Parameter | Unit | 2025 rows | 2026 rows |
|---|---|---:|---:|
| CO | ppb | 7,021 | 6,733 |
| NO₂ | ppb | 7,146 | 6,820 |
| O₃ | µg/m³ | 6,975 | 6,796 |
| PM10 | µg/m³ | 7,170 | 6,766 |
| PM2.5 | µg/m³ | 7,149 | 6,682 |
| SO₂ | ppb | 7,161 | 6,797 |

NH₃ and lead were not returned. Both files contain only location 8917 and six
parameters. Across the two files, values are non-null, non-negative, and have
no duplicate `(location_id, sensor_id, parameter, timestamp_utc)` keys.
Every `period_end_utc` is one hour after `timestamp_utc`; timestamps represent
hourly period starts. Gas units are reported in ppb, while PM2.5, PM10, and O₃
are in µg/m³.

### Decisions and limits

- **Target eligibility:** Use the labelled PM2.5 concentration records as
  candidate target data. Continue to exclude the unlabelled 2017–2023
  AQI-like OpenCity matrix from PM2.5 modelling.
- **Coverage:** Preserve missing timestamps as missing; do not interpolate
  across long outages, especially the 242-hour gap in the 2026 PM2.5 series.
  Define coverage and maximum-gap rules before training.
- **Units:** This is raw concentration data, not a calculated CPCB AQI. OpenAQ
  gas values in ppb cannot be compared directly with OpenCity gas columns in
  µg/m³; any conversion must be explicit.
- **Seam:** The 2025 OpenAQ file now overlaps the 2024–2025 OpenCity record,
  replacing the earlier January-only pull. This makes an overlap check
  possible, but no like-for-like hourly seam result is documented yet.
  OpenCity's `+0000` timestamp label still conflicts with its solar-radiation
  profile. Keep the seam unvalidated until timestamps are aligned using
  confirmed clock semantics and the overlap is audited.

## Other source conventions

- Choose and document a canonical time zone when adding CPCB or FIRMS data;
  CPCB is local IST while some other sources use UTC.
- For any future gap filling, forward-fill only with a maximum gap length;
  never fill from the future.
- Flag potential sensor faults rather than deleting plausible real extremes.

## Layout

- `raw/` — files exactly as downloaded
- `interim/` — cleaned, aligned, Parquet
