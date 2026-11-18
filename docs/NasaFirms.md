# How NASA FIRMS Data Helps an AQI Machine Learning Project

NASA FIRMS data helps an AQI model because it provides **direct satellite-based information about fire and burning sources**, which weather data alone cannot capture. *Weather data explains how pollutants move and disperse*, while FIRMS tells us when and where a large injection of smoke and particulate matter is occurring. Together, they give  model both:

- **Source information**: fires, agricultural burning, and other combustion events
- **Transport information**: wind and dispersion conditions

## Why FIRMS Matters for AQI Prediction

Standard weather data tells  whether the wind will blow, but it does not know **what is burning or where it is burning**. FIRMS fills this critical gap:

- **Captures a major pollution source**: In many regions, such as  North India, Southeast Asia, wildfires and agricultural burning are primary drivers of short-term PM2.5 spikes. FIRMS detects active fires through satellite thermal anomalies.

- **Adds predictors that weather cannot provide**: A model relying only on weather and past AQI may miss a sudden deterioration caused by a new upwind fire. FIRMS gives the model a **direct signal** that a significant new emission source has appeared.

- **Supports source attribution**: Advanced projects use FIRMS data not only to predict how much pollution occurs, but also to help identify why it is happening, for example by distinguishing biomass burning from traffic or industrial sources.

## How to Engineer Features from FIRMS Data

we will  not feed raw fire detections directly into the model. The key is to transform FIRMS data into meaningful numerical features that describe the fire's **proximity, intensity, and direction** relative to our target AQI monitor.

### 1. Proximity and Density Features

Count fire detections in zones around our AQI monitor. **For Delhi the zones must be larger than a generic 20–100 km buffer**: the main smoke source (stubble burning in Punjab and Haryana) lies roughly 100–400 km away, so small rings mostly capture *local* fires. so will Use both kinds of daily features:

- Local: `fire_count_20km`, `fire_count_50km`
- Regional: `fire_count_box_pb_hr` (a Punjab + Haryana bounding box) and `fire_count_nw_100_200km`, `fire_count_nw_200_300km`, `fire_count_nw_300_400km` (rings restricted to the north-west sector, bearing roughly 270°–360° from the monitor)

### 2. Intensity Features (Important)

FIRMS data includes **Fire Radiative Power (FRP)**, which measures the rate of energy emitted by a fire. FRP is related to the rate of fuel consumption and so to the smoke emitted, but it is an *instantaneous* reading at the satellite overpass: a daily sum depends on how many overpasses saw the fire and on cloud. will Treat it as an index of burning intensity, not as a mass of PM. Instead of only counting fires, sum the FRP of nearby fires to create features such as:

- `total_FRP_20km`
- `total_FRP_50km`
- `total_FRP_100km`

These features represent the total "smoke-generating power" near your target location.

### 3. Direction and Transport Features (Most Powerful Use)

> In this project we will combine FIRMS data with **wind direction** to create features that model **smoke transport**. 

- Identify fires that are **upwind** of our monitor based on wind direction.
- Sum the FRP of only those fires that are upwind and within a certain distance, creating features such as:
  - `upwind_FRP_50km`
  - `upwind_FRP_100km`

These features directly represent the strength of a smoke plume that may be moving toward our city.

**Caution:** the wind at the monitor *today* is a crude test of "upwind". Smoke from 250–400 km away needs roughly a day or more to arrive (at 10–15 km/h, about 1–1.5 days; verify typical speeds), so prefer wind averaged over the previous 24–48 h and fire features lagged by 0–3 days. A trajectory-based version is a later extension.



## Practical Tips for Project

- **Start simple**: Begin by adding a basic feature such as `fire_count_50km`.

- **Add complexity gradually**: Once the model works, add FRP features and then upwind/directional features. This lets you measure the incremental value of each data type.

- **Use the free API**: You can obtain a free API key from NASA FIRMS to download data programmatically. Many open-source projects also provide starting points for ingesting this data.

- **Set realistic expectations**: FIRMS is not a silver bullet. Its impact varies by region and season, and our research question 2 asks exactly this for Delhi. (An earlier draft of this note cited a Santa Cruz study without a source; it was removed until a reference is found.)

- **Always run an ablation test**: compare your model's performance with and without the FIRMS features. Be honest about sample size: only about three burning seasons will exist (2024, 2025 and the live 2026), so use rolling-origin evaluation and report the number of seasons and days behind every claim.

## Summary

NASA FIRMS provides the **source term** for our AQI model. By intelligently engineering features from fire location, intensity, and direction relative to wind, we can give our machine learning model the information it needs to anticipate pollution spikes that weather data alone would miss.

In short:

- **Weather data**: explains how pollutants move and disperse
- **FIRMS data**: tells the model when and where pollution sources appear
- **Combined**: lets the AQI model see both the **source** and the **transport mechanism**

## Data handling rules (alignment and leakage)

- **Timestamps:** FIRMS gives `acq_date` and `acq_time` (HHMM, UTC, zero-padded). Combine them, then convert to IST (+5:30) before joining anything.

- **Availability:** at issue time *t* use only detections acquired at or before *t*, minus the processing latency of the product (near-real-time data arrives hours after the overpass; verify in the FIRMS documentation).

- **Product consistency:** FIRMS offers near-real-time and standard-processing archives. Train and serve on the same product, or measure the difference first.

- **Sensor choice:** pick one (VIIRS has finer 375 m detections, MODIS is 1 km) and keep it; check the `confidence` and `daynight` attributes in the FIRMS attribute table before filtering.

- **A zero count is not a "no fire" fact:** cloud hides fires and detections are overpass events, so keep a notion of valid coverage rather than reading zeros literally.

- **API:** free `MAP_KEY` in `.env`; at most 5,000 transactions per 10 minutes and multi-day requests count as several, so fetch in chunks with a bounding box.

## Status in this project

| Item | Status |
|---|---|
| Key | collected |
| Ingest module | `nasafirms.py` exists, not yet audited |
| Features | start Week 3 (after baselines); order: regional box counts, then NW-sector rings, then FRP, then lags |
| Evaluation | ablation with rolling-origin folds, sample sizes stated |
