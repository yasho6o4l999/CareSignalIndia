SELECT
    round(min(minimum_value), 1) AS minimum_temperature,
    round(avg(average_value), 1) AS average_temperature,
    round(max(maximum_value), 1) AS maximum_temperature
FROM read_parquet('{environmental_metrics_path}')
WHERE decision_date = ?
  AND metric = 'temperature_2m';
