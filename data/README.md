# Data

Raw and interim data are **not committed** (see `.gitignore`). This file is the
data dictionary: one entry per source, filled in as each source is ingested.

| Source | What | Access | Terms checked | Status |
|---|---|---|---|---|
| CPCB station readings (via OpenCity / data.gov.in / OpenAQ) | Hourly pollutants per station | TBD | no | not started |
| Weather (Open-Meteo / ERA5) | Temp, humidity, wind, rain, pressure | TBD | no | not started |
| NASA FIRMS | Active-fire detections (Punjab/Haryana box) | Free MAP_KEY | no | not started |

## Conventions (to be settled during the audit)

- **Time zone:** one canonical zone for everything (CPCB is local IST; weather/FIRMS are often UTC). Decision: _TBD_
- **Gaps:** forward-fill only, with a maximum gap length; never fill from the future. Decision: _TBD_
- **Sensor faults:** flag, don't delete real extremes. Rules: _TBD_
- **Station(s):** _TBD_

## Layout

- `raw/` — files exactly as downloaded
- `interim/` — cleaned, aligned, Parquet
