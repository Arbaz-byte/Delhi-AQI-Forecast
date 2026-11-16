# How Weather Data Helps an AQI Machine Learning Project

> **Project note (Delhi PM2.5).** Read this note together with `notebooks/01_weather_audit.ipynb`. Two warnings from that audit: (1) wind speed in the Open-Meteo archive has a **level shift at about 2024-11-06** (about −2.5 km/h, source unverified, open item O1), so wind statistics that mix the two periods are unsafe until O1 is resolved; (2) `visibility` is empty in the archive.

Weather data is one of the most important input groups for AQI prediction because it controls how pollutants are **emitted, transported, diluted, transformed, and removed** from the atmosphere. Weather does not usually tell you where pollution comes from, but it strongly controls what happens to pollution after it is emitted. This makes weather essential for predicting both **average AQI levels** and **short-term pollution spikes**.

In simple terms:

- **Emission sources** determine how much pollution is released.
- **Weather** determines where that pollution goes, how long it stays, and how it changes chemically.
- **AQI** is the observed result of both.

## Why Weather Matters for AQI Prediction

AQI is not only a function of emissions. The same amount of traffic, industrial activity, or burning can produce very different AQI values under different weather conditions. Weather affects AQI through several physical and chemical mechanisms:

- **Dispersion and dilution**: Wind and atmospheric turbulence mix pollutants into cleaner air. Stronger winds and deeper mixing usually reduce local pollutant concentrations.

- **Transport**: Wind direction moves pollution from one area to another. A monitor can have poor AQI because pollution was produced far upwind.

- **Stagnation**: Low wind speed and stable atmospheric conditions trap pollutants near the surface, causing rapid AQI deterioration.

- **Vertical mixing**: Boundary layer height controls the volume of air available for dilution. A shallow boundary layer concentrates pollutants; a deep boundary layer dilutes them.

- **Chemical transformation**: Temperature, sunlight, and humidity affect secondary pollutant formation, such as ozone and secondary aerosols.

- **Removal by precipitation**: Rain can wash out particulate matter and soluble gases, improving AQI.

- **Deposition**: Dry deposition removes pollutants at the surface, and its rate depends on turbulence and surface conditions.

Because of these mechanisms, weather variables are among the strongest predictors in most AQI forecasting models.

## Key Weather Variables and Their Role

### 1. Wind Speed

Wind speed is one of the most important predictors of pollutant concentration.

- **Higher wind speed** usually increases dispersion and lowers AQI.
- **Low wind speed** promotes stagnation and allows pollutants to accumulate.
- Very low wind speed combined with a stable atmosphere can cause severe pollution episodes.

Useful features include:

- `wind_speed`
- `wind_speed_lag_1`
- `wind_speed_rolling_mean_24h`
- `low_wind_flag` or `stagnation_index`

### 2. Wind Direction

Wind direction determines **where pollution comes from**.

- It helps identify whether a monitor is downwind of traffic, industry, a city center, or a fire.
- Wind direction is especially powerful when combined with source data such as NASA FIRMS fire detections.
- Directional features can represent transport from known source regions.

Useful features include:

- `wind_u`, `wind_v` (preferred: they keep the speed)
- `wind_direction_sin`, `wind_direction_cos` (optional, only when speed > 0)
- `upwind_fire_FRP`
- `wind_from_industrial_zone_flag`

Prefer **u/v wind components** (u = −speed·sin θ, v = −speed·cos θ, where θ is the direction the wind comes *from*), because they keep the speed. Sine and cosine of the direction alone throw the speed away and are meaningless at calm (decision D4). In this dataset north is stored as 360, never 0, so use `direction % 360`.

### 3. Temperature

Temperature affects both atmospheric stability and chemistry.

- High surface temperature can increase vertical mixing, which may dilute pollutants.
- Temperature inversions, where warmer air sits above cooler air, trap pollutants near the surface.
- High temperature and strong sunlight promote photochemical reactions, increasing ozone formation.
- Temperature also affects secondary aerosol formation and partitioning.

Useful features include:

- `temperature_2m`
- `temperature_lag_1`
- `temperature_change_24h`
- `inversion_strength` if upper-air data is available

### 4. Relative Humidity

Humidity affects aerosol growth and chemical reactions.

- High humidity can promote hygroscopic growth of particles, increasing PM2.5 or PM10 measurements (whether this shows up in *measured* PM2.5 depends on how the instrument conditions its sample air, so treat it as a hypothesis).
- Humidity affects secondary aerosol formation and ozone chemistry.
- Very low humidity may be associated with dust and wildfire conditions.

Useful features include:

- `relative_humidity`
- `relative_humidity_rolling_mean_24h`
- `high_humidity_flag`

### 5. Precipitation

Precipitation is a natural removal mechanism.

- Rain washes out particulate matter and soluble gases.
- After significant rainfall, AQI often improves.
- The effect depends on rainfall intensity and duration.

Useful features include:

- `precipitation`
- `precipitation_last_24h`
- `rain_flag`
- `hours_since_rain`

### 6. Boundary Layer Height

Boundary layer height is one of the most physically meaningful weather variables for AQI.

- A **shallow boundary layer** means pollutants are trapped in a small volume of air, increasing concentration.
- A **deep boundary layer** means pollutants are mixed into a larger volume, reducing concentration.
- Morning and evening transitions can cause rapid changes in AQI.

Useful features include:

- `boundary_layer_height`
- `boundary_layer_height_lag_1`
- `ventilation_coefficient` = wind speed × boundary layer height

The ventilation coefficient is a useful derived feature because it combines mixing volume and transport.

### 7. Surface Pressure and Synoptic Patterns

Pressure patterns influence stagnation and transport.

- High-pressure systems often bring calm, stable conditions and poor dispersion.
- Low-pressure systems can bring wind and precipitation, improving AQI.
- Pressure tendency, such as falling or rising pressure, can indicate changing weather regimes.
- **Delhi caveat:** raw pressure is dominated by the seasonal heat low (965–975 hPa in May–August against ~990 hPa in winter), so use *deseasonalised* pressure and 3 h / 24 h changes, not the raw level.

Useful features include:

- `surface_pressure`
- `pressure_change_3h`
- `pressure_change_24h`

### 8. Solar Radiation

Solar radiation drives photochemistry.

- Strong sunlight promotes ozone formation.
- Radiation interacts with temperature and humidity in secondary pollutant formation.
- It can also affect boundary layer development.

Useful features include:

- `shortwave_radiation`
- `solar_radiation_rolling_mean`
- `clear_sky_index`

## How Weather Data Helps Machine Learning Models

Weather data helps an ML model in three main ways:

1. **Direct prediction of concentration changes**: Wind, boundary layer height, and precipitation directly affect pollutant concentrations.
2. **Capturing stagnation and accumulation**: Low wind, shallow boundary layer, and high pressure indicate conditions where pollution can build up.
3. **Explaining transport and chemistry**: Wind direction, temperature, humidity, and radiation help the model learn where pollution comes from and how it transforms.

Weather variables are especially useful when combined with:

- **Lag features**: AQI and weather from previous hours or days.
- **Rolling statistics**: 24-hour means, maximums, and trends.
- **Interaction features**: wind speed × boundary layer height, temperature × radiation, humidity × PM2.5 lag.
- **Source data**: wind direction combined with FIRMS fire data to model smoke transport.

## Practical Feature Engineering Tips

- **Use lag and rolling features**: Pollution responds to weather with delays. Create lagged and rolling weather features such as `wind_speed_lag_6`, `boundary_layer_height_rolling_mean_24h`, and `precipitation_last_24h`.

- **Encode wind direction properly**: use u/v components (or sin/cos when speed > 0), never raw degrees.

- **Create physically meaningful interactions**: Examples include ventilation coefficient, stagnation index, and upwind source strength.
- **Align timestamps carefully**: Weather data, AQI data, and FIRMS data must be matched to the same time zone and resolution. Here: Open-Meteo is IST (naive), the CPCB files are IST labelled `+0000`, FIRMS is UTC. 15-minute station data is averaged over the *previous* hour and stamped at the hour end (decision D11).

- **Handle missing values**: forward-fill only, with a maximum gap length, plus a missing-value indicator. Never interpolate across a gap, because that uses the future.
- **Use forecast weather for real forecasting**: if you want to predict future AQI, use weather forecasts rather than only historical observations. Two settings must be kept apart: **(a)** weather observed up to the issue time *t*, and **(b)** archived forecasts issued at or before *t*. Reanalysis at *t + h* is not a forecast and must never be used as one. In our weather audit, wind speed kept only 0.37 / 0.13 / 0.06 autocorrelation at 24 / 48 / 72 h once the daily and annual cycles were removed, so setting (a) says little about tomorrow's ventilation; setting (b) matters (Open-Meteo documents historical-forecast and single-run archives; check the lead-time semantics first).
- **Run ablation tests**: Compare model performance with and without weather features to measure their contribution.

## Summary

Weather data helps AQI prediction because it controls the **transport, dispersion, transformation, and removal** of pollutants. It does not usually tell you where pollution is emitted, but it tells you what happens to pollution after emission.

In short:

- **Weather data**: explains how pollutants move, mix, react, and are removed
- **FIRMS data**: tells the model when and where fire-based pollution sources appear
- **AQI history**: captures persistence and local emission patterns
- **Combined**: gives the model a complete picture of **source, transport, transformation, and observed outcome**

## Status in this project

| Variable | Source | Status |
|---|---|---|
| temperature_2m, relative_humidity_2m, rain, wind_speed_10m, wind_direction_10m, surface_pressure | Open-Meteo archive, 2003 to Oct 2026 | ingested and audited |
| AT, RH, WS (m/s), WD, RF, SR, BP | on-site CPCB station, OpenCity 2024–25 files | to be audited; check units per file |
| boundary_layer_height, dew point, cloud cover, shortwave radiation | Open-Meteo (archive or forecast) | availability **unchecked** (open item O2) |
| ventilation coefficient (wind × boundary-layer height) | derived | blocked until boundary-layer height is available; 10 m wind only approximates the layer-mean wind |
| archived weather forecasts | Open-Meteo historical-forecast / single-run archives | to check (open item O3) |
