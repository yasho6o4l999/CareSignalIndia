COPY (
    WITH metric_values AS (
        SELECT
            CAST(timezone('{decision_timezone}', c.observed_at) AS DATE) AS decision_date,
            c.city_id,
            metric,
            metric_value
        FROM read_parquet('{city_conditions_path}') c
        CROSS JOIN LATERAL (
            VALUES
                ('apparent_temperature', apparent_temperature),
                ('temperature_2m', temperature_2m),
                ('precipitation', precipitation),
                ('daily_precipitation_sum', daily_precipitation_sum),
                ('daily_min_temperature', daily_min_temperature),
                ('daily_max_temperature', daily_max_temperature),
                ('daily_temperature_range', daily_temperature_range),
                ('apparent_temperature_uplift', apparent_temperature_uplift),
                ('relative_humidity', relative_humidity),
                ('wind_speed', wind_speed),
                ('pm2_5', pm2_5),
                ('pm10', pm10),
                ('pm2_5_rolling_24h', pm2_5_rolling_24h)
        ) metrics(metric, metric_value)
    )
    SELECT
        m.decision_date,
        m.city_id,
        m.metric,
        min(m.metric_value) AS minimum_value,
        avg(m.metric_value) AS average_value,
        max(m.metric_value) AS maximum_value,
        b.average_value AS historical_average,
        b.p10_value AS historical_p10,
        b.p90_value AS historical_p90,
        b.p95_value AS historical_p95,
        b.minimum_value AS historical_minimum,
        b.maximum_value AS historical_maximum
    FROM metric_values m
    LEFT JOIN read_parquet('{historical_baselines_path}') b
        ON m.city_id = b.city_id
       AND month(m.decision_date) = b.month
       AND m.metric = b.metric
    GROUP BY m.decision_date, m.city_id, m.metric, b.average_value, b.p10_value, b.p90_value,
             b.p95_value, b.minimum_value, b.maximum_value
) TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD);
