COPY (
    WITH metric_values AS (
        SELECT
            city_id,
            observed_at,
            metric,
            metric_value
        FROM read_parquet('{city_conditions_path}')
        CROSS JOIN LATERAL (
            VALUES
                ('apparent_temperature', apparent_temperature),
                ('precipitation', precipitation),
                ('pm2_5', pm2_5)
        ) metrics(metric, metric_value)
    ),
    evaluated AS (
        SELECT
            r.*,
            m.observed_at,
            m.metric_value,
            lag(m.observed_at) OVER (
                PARTITION BY r.ruleset_version, r.rule_id, r.city_id
                ORDER BY m.observed_at
            ) AS previous_observed_at,
            CASE
                WHEN r.operator = 'greater_than_or_equal' THEN m.metric_value >= r.threshold
                WHEN r.operator = 'less_than_or_equal' THEN m.metric_value <= r.threshold
                ELSE false
            END AS is_breach
        FROM metric_values m
        INNER JOIN read_parquet('{rules_path}') r
            ON m.city_id = r.city_id
           AND m.metric = r.metric
           AND month(m.observed_at) = r.month
    ),
    grouped AS (
        SELECT
            *,
            sum(
                CASE
                    WHEN NOT is_breach THEN 1
                    WHEN previous_observed_at IS NULL THEN 1
                    WHEN date_diff('hour', previous_observed_at, observed_at) <> 1 THEN 1
                    ELSE 0
                END
            ) OVER (
                PARTITION BY ruleset_version, rule_id, city_id
                ORDER BY observed_at
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS streak_group
        FROM evaluated
    ),
    qualifying_streaks AS (
        SELECT
            ruleset_version,
            rule_id,
            city_id,
            metric,
            operator,
            operator_label,
            threshold,
            persistence_hours,
            severity,
            streak_group,
            min(observed_at) AS window_start,
            max(observed_at) AS window_end,
            count(*) AS observed_persistence_hours,
            min(metric_value) AS minimum_metric_value,
            max(metric_value) AS maximum_metric_value
        FROM grouped
        WHERE is_breach
        GROUP BY ALL
        HAVING count(*) >= persistence_hours
    )
    SELECT
        *,
        concat(
            rule_id, ': ', metric, ' remained ', operator_label, ' ', threshold,
            ' for ', observed_persistence_hours, ' consecutive forecast hours in ', city_id, '.'
        ) AS trigger_explanation
    FROM qualifying_streaks
) TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD);

