WITH relevant_metrics AS (
    SELECT DISTINCT city_id, unnest(metrics) AS metric
    FROM read_parquet('{environmental_conditions_path}')
    WHERE decision_date = ?
      AND (? IS NULL OR city_id = ?)
)
SELECT
    m.city_id,
    CASE m.metric
        WHEN 'apparent_temperature' THEN 'Apparent Temperature'
        WHEN 'temperature_2m' THEN 'Temperature'
        WHEN 'daily_max_temperature' THEN 'Daily Maximum Temperature'
        WHEN 'daily_min_temperature' THEN 'Daily Minimum Temperature'
        WHEN 'daily_temperature_range' THEN 'Daily Temperature Range'
        WHEN 'apparent_temperature_uplift' THEN 'Apparent Temperature Uplift'
        WHEN 'daily_precipitation_sum' THEN 'Daily Precipitation'
        WHEN 'relative_humidity' THEN 'Relative Humidity'
        WHEN 'wind_speed' THEN 'Wind Speed'
        WHEN 'pm2_5' THEN 'PM2.5'
        WHEN 'pm10' THEN 'PM10'
        WHEN 'pm2_5_rolling_24h' THEN 'PM2.5 Rolling 24h'
        ELSE m.metric
    END AS metric,
    CASE
        WHEN m.metric LIKE '%temperature%' THEN '°C'
        WHEN m.metric LIKE '%precipitation%' THEN 'mm'
        WHEN m.metric = 'relative_humidity' THEN '%'
        WHEN m.metric = 'wind_speed' THEN 'km/h'
        WHEN m.metric IN ('pm2_5', 'pm10', 'pm2_5_rolling_24h') THEN 'µg/m³'
    END AS unit,
    round(m.minimum_value, 1) AS forecast_minimum,
    round(m.average_value, 1) AS forecast_average,
    round(m.maximum_value, 1) AS forecast_maximum,
    round(m.historical_average, 1) AS historical_average,
    round(m.historical_p10, 1) AS historical_p10,
    round(m.historical_p90, 1) AS historical_p90,
    round(m.historical_p95, 1) AS historical_p95,
    round(m.historical_minimum, 1) AS historical_minimum,
    round(m.historical_maximum, 1) AS historical_maximum
FROM read_parquet('{environmental_metrics_path}') m
INNER JOIN relevant_metrics r USING (city_id, metric)
WHERE m.decision_date = ?
ORDER BY m.city_id, m.metric;
