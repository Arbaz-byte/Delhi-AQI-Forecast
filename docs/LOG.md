# Project log
---

## 2026-10-26 (Mon)
- **Did:** created the repo, layout, licence, README; first Open-Meteo fetch.
- **Next:** weather ingest module.

## 2026-10-27 (Tue)
- **Did:** `open_meteo.py`: fetch, validate, write raw parquet + meta JSON.
- **Found:** `visibility` is empty in the archive; 70,512 rows validated.

## 2026-10-28 (Wed)
- **Did:** weather audit notebook (11 steps) and the reusable `aqi.audit` helpers.
- **Found:** wind speed drops ~30 % from ~2024-11-06 in every season (looks like a source change); everything else physical; weather at issue time says little about tomorrow's wind.
- **Decided:** D1–D8 (see `data/README.md`). Open: O1–O4.

## 2026-10-30 (Fri)
- **Did:** researched station PM2.5 sources, licences, keys.
- **Found:** hourly PM2.5 concentration exists from 2024-01 (15-min files); the 2017–2023 files are a wide "AQI" table; timestamps are IST labelled `+0000`; PM2.5 updates hourly at :45; BP column is in hPa. Diwali 2026 is Sun 8 Nov.
- **Next:** Week 1 plan in `PLAN.md`; start Sun 1 Nov.

## 2026-11-01 – 2026-11-02
- **Did:** nothing on the project (planned days missed).
- **Decided:** rebase Sprint 1 to Tue 3 Nov → Mon 9 Nov; work list is now `TICKETS.md` (AQI-01 … AQI-11). Nothing was cut except the live logger, which became a stretch ticket.
- **Next:** Tue 3 Nov: AQI-01 reading, AQI-02 setup and first look.

## 2026-11-03 – 2026-11-06
- **Did:** Reading A (benchmarks, availability time): theory only. Moved to data gathering on 6 Nov.
- **Lost:** most of the week; no tickets completed.

## 2026-11-07 (Sat)
- **Did:** downloaded the OpenCity files for Ashok Vihar.
- **Found:** the two files are very different. 2017–2023 is a month × day × hour matrix of what looks like AQI; 2024–25 is a tidy 15-minute table with all pollutants and on-site weather.

## 2026-11-08 – 2026-11-09
- On vacation. 9 Nov: inventoried the repo; all API keys are in `.env`; data.gov.in parked (server down, OpenAQ covers live data); added theory notes (`Weather`, `PastAQI`, `NasaFirms`) under `docs/`.

## 2026-11-10 (Tue)
- **Did:** wrote `notebooks/02_opencity_audit.ipynb` (OpenCity + OpenAQ), `openaq.py` and the matrix reader in `opencity.py`; fetched OpenAQ for Ashok Vihar, 1 Nov – 31 Dec 2025.
- **Found:**
  - OpenCity 2024–25 is Ashok Vihar (`site_1420`): 70,176 rows, 2024-01-01 00:00 to 2025-12-31 23:45 at 15 minutes with no missing timestamps; PM2.5 1–965 µg/m³, 1,582 null cells.
  - 2017–2023 is AQI-like: values 1–500 with 1,148 capped at exactly 500; numbers only from 2018-02-01 09:00 to 2023-12-31 23:00.
  - Solar radiation peaks at 12:00 on the stored clock, so the stored digits are IST and the `+0000` label is wrong.
  - PM2.5 changes at :00 in 78 % of cases and at :45 in 18 %.
  - The `BP (mmHg)` column holds hPa-sized values (973–986).
  - OpenAQ: CPCB location 8917 (Ashok Vihar), sensors listed from 2025-02-19; Nov–Dec 2025 PM2.5 coverage 95.8 %, longest gap 14 h; the 23:00 hour of the window is missing.
- **Decided:** exclude 2017–2023 from the PM2.5 target; clock = IST, pending the OpenCity–OpenAQ seam check.
- **Received, not yet applied:** updated `opencity.py` (`read_15min`, `to_hourly`), `openaq.py` (location filter, window-end fix), `tests/test_opencity.py`, rebuilt notebook.

## 2026-11-11 – 2026-11-14
- No project work logged.

## 2026-11-15 (Sun)
- **Found:** the plan did not fit the time: two projects every day, DSA, tuition, and no ML/DL theory since starting the projects. The Fundus tickets are theory-heavy, which made them the slowest.

- **Decided:** one project per day from Mon 16 Nov: **AQI on Mon / Wed / Fri, Fundus on Tue / Thu / Sat**; each session is 3–4 h plus a 1 h close-out; **Sunday has both projects, 3 h each**; theory and rest in the remaining time. Rules: one project per weekday; no catch-up stacking; a daily close-out (commit, LOG entry, docs, first ticket of the next session). **Checkpoint Sun 29 Nov:** if fewer than 70 % of planned sessions happened, cut sessions to 3 h flat, then drop one Sunday block.


## 2026-11-18 (Wed)
- **Did:** re-executed the Open-Meteo weather audit; added OpenCity legacy/tidy readers and tests; added the OpenAQ hourly fetcher; renamed the data.gov.in snapshot client to `aqi_govt.py`; updated the OpenAQ data notes.

- **Found:** OpenCity tests pass (10 passed). The refreshed OpenAQ pulls contain only Ashok Vihar location 8917: PM2.5 coverage is 94.28% in the 2025 observed span (longest missing run 61 h) and 87.15% in 2026 (242 h). The data.gov.in request ended in `ReadTimeout` before a response was received.

- **Decided:** keep data.gov.in parked for now. A 2025 OpenCity–OpenAQ overlap is available, but the timestamp convention and hourly seam are not yet validated; do not concatenate the sources yet.