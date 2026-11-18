# How Past AQI Data Helps an AQI Machine Learning Project

> **Project note (Delhi PM2.5).** In this repo the modelled target is **hourly PM2.5 in µg/m³** (decision D10), not the AQI index. The AQI is a maximum over pollutant sub-indices and, as far as I know, uses a 24-hour average for particulates, so it is smoother and a different target. Wherever this note says "AQI", read "PM2.5"; the AQI category is computed afterwards for display.

> **Lags are always relative to the issue time *t*:** `lag_k` is the value at *t − k*, and the target is the value at *t + h* with h ∈ {24, 48, 72}. Short lags (1–6 h) are very informative for 1–6 h forecasts; at 24–72 h persistence is much weaker, and whether the model beats it is research question 1.

Past AQI data is one of the strongest and most reliable input groups for AQI prediction because air pollution is highly **persistent over time**. If AQI is high now, it is often likely to remain high for the next few hours or days unless weather or emissions change significantly. 

Past AQI captures the combined effect of all unobserved factors: local emissions, traffic patterns, industrial activity, meteorology, and pollution transport. In practice, lagged AQI features are often among the most important predictors in AQI forecasting models.

In simple terms:

- **Past AQI** summarizes what has already happened.
- **Weather** explains how pollution is moving and dispersing.
- **FIRMS** explains when and where fire-based sources appear.
- **Future AQI** is strongly influenced by the recent history of AQI itself.

## Why Past AQI Matters for Prediction

AQI is not random from hour to hour. It has strong temporal structure due to several physical and behavioral mechanisms:

- **Pollutant lifetime**: PM2.5 and other pollutants can remain in the atmosphere for hours to days, so current concentrations depend on recent concentrations.

- **Emission persistence**: Traffic, industry, cooking, and residential emissions follow daily and weekly routines.

- **Meteorological persistence**: Weather patterns such as stagnation, inversions, and wind regimes often last for multiple hours or days.

- **Boundary layer cycles**: Daily cycles of boundary layer growth and collapse create repeating AQI patterns.

- **Seasonal cycles**: Heating, dust, crop burning, and photochemistry create seasonal AQI patterns.

- **Transport persistence**: Pollution arriving from upwind regions can continue for extended periods.

- **Autocorrelation**: AQI time series are strongly autocorrelated, especially at short lags such as 1 to 6 hours.

Because of these mechanisms, past AQI acts as a compact summary of many unobserved processes. It is often called a **persistence signal** or **autoregressive information**.

## Key Ways Past AQI Helps

### 1. Captures Persistence and Autocorrelation

The most recent AQI values are usually the best short-term predictors of future AQI.

- `AQI_lag_1` captures the immediate previous hour or day.
- `AQI_lag_3`, `AQI_lag_6`, and `AQI_lag_24` capture longer memory.
- Short lags are especially useful for hourly forecasting.
- Daily lags capture daily cycles and day-to-day persistence.

Strong autocorrelation means that even simple lag features can substantially improve model performance.

### 2. Captures Daily and Weekly Patterns

AQI often follows regular cycles:

- Morning and evening traffic peaks.
- Daytime boundary layer growth and nighttime collapse.
- Weekday versus weekend emission differences.
- Industrial and commercial activity schedules.

Past AQI at the same hour on previous days can capture these cycles. Useful features include:

- `AQI_same_hour_yesterday`
- `AQI_same_hour_last_week`
- `hour_of_day`
- `day_of_week`
- `is_weekend`

Cyclical encodings such as sine and cosine of hour and day can help models learn smooth periodic patterns.

### 3. Captures Trends and Momentum

The direction and speed of change in AQI can be informative.

- A rapidly rising AQI may indicate an approaching smoke plume, stagnation event, or new emission source.
- A rapidly falling AQI may indicate rain, wind, or source shutdown.
- Trends help the model distinguish between stable and changing conditions.

Useful features include:

- `AQI_diff_1h` = AQI(t) − AQI(t−1)
- `AQI_diff_24h` = AQI(t) − AQI(t−24)
- `AQI_rate_of_change`
- `AQI_trend_6h`

### 4. Captures Recent Pollution Accumulation

Rolling statistics summarize recent pollution burden.

- Rolling means smooth out noise and show the recent average level.
- Rolling maximums capture recent peaks.
- Rolling minimums capture baseline conditions.
- Exponentially weighted means give more weight to recent observations.

Useful features include:

- `AQI_rolling_mean_6h`
- `AQI_rolling_mean_24h`
- `AQI_rolling_max_24h`
- `AQI_rolling_min_24h`
- `AQI_ewma_24h`

These features help the model understand whether pollution is accumulating or clearing.

### 5. Captures Anomalies and Regime Changes

Past AQI can help detect unusual conditions relative to normal patterns.

- Compare current AQI with its recent average.
- Compare current AQI with the same hour on previous days.
- Flag sudden spikes or drops.

Useful features include:

- `AQI_anomaly_24h` = AQI − AQI_rolling_mean_24h
- `AQI_ratio_to_24h_mean`
- `AQI_spike_flag`
- `AQI_drop_flag`

Anomaly features can help the model respond to unusual events such as fires, dust storms, or industrial accidents.

### 6. Acts as a Proxy for Unobserved Emissions

Past AQI indirectly reflects emissions that are not directly measured.

- Traffic intensity.
- Industrial activity.
- Residential heating or cooking.
- Waste burning.
- Agricultural burning.
- Construction dust.

Even if these sources are not available as explicit features, their combined effect is embedded in the AQI history. This makes past AQI a powerful proxy variable.

### 7. Interacts with Weather and FIRMS Data

Past AQI becomes even more useful when combined with weather and source data.

- **AQI lag × wind speed**: High past AQI with low wind suggests continued accumulation.
- **AQI lag × boundary layer height**: Shallow boundary layer with high past AQI suggests severe stagnation.
- **AQI lag × upwind fire FRP**: Recent high AQI plus strong upwind fires suggests continued smoke impact.
- **AQI lag × precipitation**: Recent high AQI followed by rain suggests likely improvement.

Interaction features help the model learn physically meaningful combined effects.

## Practical Feature Engineering Tips

- **Create multiple lag features**: Will create a lags at 1, 3, 6, 12, 24, and 48 hours or days depending on our forecast horizon.
- **Use rolling statistics**: Include rolling means, maximums, minimums, and standard deviations over 6h, 12h, 24h, and 7 days.
- **Use exponentially weighted features**: EWMA features often work well for noisy pollution time series.
- **Add same-hour historical features**: Same hour yesterday and same hour last week capture daily and weekly cycles.
- **Encode time cyclically**: Use sine and cosine for hour of day, day of week, and month.
- **Include trend and momentum features**: Differences and rates of change help capture rapid deterioration or improvement.
- **Avoid data leakage**: When predicting future AQI, only use past AQI values that would actually be available at prediction time.
- **Handle missing values carefully**: forward-fill only, with a maximum gap length, plus a missing-value indicator. **Do not interpolate across gaps**: linear interpolation uses the value *after* the gap, which is the future (project rule in `data/README.md`).
- **Check stationarity**: AQI distributions may change by season or year. Consider normalization, differencing, or seasonal features.
- **Run ablation tests**: Compare model performance with and without past AQI features to measure their contribution.


## Summary

Past AQI data helps prediction because pollution is persistent and because AQI history embeds the combined effect of emissions, weather, transport, and human activity. It provides the model with **memory** and **context**.

In short:

- **Past AQI**: captures persistence, trends, cycles, and unobserved emissions
- **Weather data**: explains how pollutants move, mix, react, and are removed
- **FIRMS data**: tells the model when and where fire-based sources appear
- **Combined**: gives the model a complete picture of **history, source, transport, transformation, and observed outcome**

## Project mapping (what we will actually build)

| Idea in this note | Our version | Notes |
|---|---|---|
| Lags | PM2.5 at t−1, 2, 3, 6, 12, 24, 48, 72 h | available at issue time only |
| Rolling statistics | mean, std, max over 6, 24, 72 h | trailing windows, never centred |
| Same hour yesterday / last week | t+h−168 (last week); "yesterday" equals persistence at h = 24/48/72 | last week is a *baseline* too |
| Cyclical time | hour and day-of-year as sin/cos; weekend, holiday and Diwali flags | few Diwali seasons exist, so claims there are weak |
| Anomaly and spike flags | PM2.5 minus its 24 h mean; flag, never delete, real spikes | Diwali night is real |
| Baselines these features must beat | persistence, trailing 24 h mean, same hour last week, climatology | skill score = 1 − MAE_model / MAE_baseline |
| Ablation | with/without lag features, weather, fires | rolling-origin folds; report sample sizes |
