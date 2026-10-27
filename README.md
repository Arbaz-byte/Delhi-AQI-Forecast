# Delhi AQI Forecasting

Forecasting Delhi PM2.5 **24–72 hours ahead** with **prediction intervals whose
coverage is actually measured** — built from public station data, weather and
satellite fire detections.

> **Status: data phase.** Nothing is modelled yet. This repo currently covers
> data gathering, understanding and preprocessing. Results sections will be
> added when they exist.

## Why this project

Plenty of AQI predictors exist. The goal here is honest evaluation on real,
messy data: fair baselines (persistence first), time-correct validation, and
intervals whose claimed confidence can be checked — including where the model
fails (Diwali spikes, wind shifts, rare extremes).

## Current scope (v1)

1. Gather data from public APIs / downloads (station readings, weather, fires)
2. Audit it: gaps, units, time zones, sensor faults
3. Clean and align it into one time-indexed dataset

Modelling, uncertainty and the dashboard come after this phase is solid.

## Setup

```bash
git clone https://github.com/<Arbaz-byte>/delhi-aqi-forecast.git
cd delhi-aqi-forecast
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
cp .env.example .env             # add keys only when a source needs one
```

## Layout

```
delhi-aqi-forecast/
├── README.md
├── LICENSE
├── pyproject.toml
├── .env.example
├── data/
│   ├── README.md        data dictionary and decisions
│   ├── raw/             as downloaded (not committed)
│   └── interim/         cleaned, aligned Parquet (not committed)
├── notebooks/           audit and exploration
└── src/aqi/
    └── ingest/          one module per data source
```

Folders are added only when the work needs them.

## Data and licensing

Raw datasets are not redistributed. Each source's terms are checked and
recorded in `data/README.md`, and the repo ships download code and attribution
instead of data. API keys live in `.env` and are never committed.

## License

Code: [MIT](LICENSE). Data remains under each source's own terms.
