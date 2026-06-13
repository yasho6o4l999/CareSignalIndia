SELECT
    city_id,
    month,
    metric,
    round(average_value, 1) AS average_value,
    round(p90_value, 1) AS p90_value,
    round(p95_value, 1) AS p95_value,
    sample_count,
    historical_years,
    baseline_start_date,
    baseline_end_date
FROM read_parquet('{historical_baselines_path}')
WHERE (? IS NULL OR city_id = ?)
ORDER BY city_id, month, metric;

