WITH relevant_metrics AS (
    SELECT DISTINCT city_id, unnest(metrics) AS metric
    FROM read_parquet('{environmental_conditions_path}')
    WHERE decision_date = ?
      AND (? IS NULL OR city_id = ?)
)
SELECT
    m.city_id,
    m.metric,
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
