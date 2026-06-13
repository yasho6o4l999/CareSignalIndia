COPY (
    WITH metric_values AS (
        SELECT
            city_id,
            observed_date,
            metric,
            metric_value
        FROM read_parquet('{history_path}', hive_partitioning = true)
        CROSS JOIN LATERAL (
            VALUES
                ('temperature_2m', temperature_2m),
                ('daily_max_temperature', temperature_2m),
                ('daily_min_temperature', minimum_temperature_2m),
                ('daily_temperature_range', temperature_range),
                ('daily_precipitation_sum', precipitation)
        ) metrics(metric, metric_value)
    )
    SELECT
        city_id,
        month(observed_date) AS month,
        metric,
        avg(metric_value) AS average_value,
        quantile_cont(metric_value, 0.10) AS p10_value,
        quantile_cont(metric_value, 0.90) AS p90_value,
        quantile_cont(metric_value, 0.95) AS p95_value,
        min(metric_value) AS minimum_value,
        max(metric_value) AS maximum_value,
        count(*) AS sample_count,
        count(DISTINCT year(observed_date)) AS historical_years,
        min(observed_date) AS baseline_start_date,
        max(observed_date) AS baseline_end_date
    FROM metric_values
    GROUP BY city_id, month(observed_date), metric
) TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD);
