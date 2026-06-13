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
                ('temperature_2m', temperature_2m),
                ('precipitation', precipitation),
                ('pm2_5', pm2_5)
        ) metrics(metric, metric_value)
    ),
    applicable_rules AS (
        SELECT
            r.* EXCLUDE (threshold),
            r.threshold AS configured_threshold,
            CASE
                WHEN r.comparison = 'absolute' THEN r.threshold
                WHEN r.baseline_percentile = 'p90' THEN b.p90_value
                WHEN r.baseline_percentile = 'p95' THEN b.p95_value
            END AS effective_threshold,
            b.average_value AS baseline_average,
            b.p90_value AS baseline_p90,
            b.p95_value AS baseline_p95,
            b.sample_count AS baseline_sample_count,
            b.historical_years
        FROM read_parquet('{rules_path}') r
        LEFT JOIN read_parquet('{historical_baselines_path}') b
            ON r.city_id = b.city_id
           AND r.month = b.month
           AND r.metric = b.metric
        WHERE r.comparison = 'absolute' OR b.city_id IS NOT NULL
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
                WHEN r.operator = 'greater_than_or_equal' THEN m.metric_value >= r.effective_threshold
                WHEN r.operator = 'less_than_or_equal' THEN m.metric_value <= r.effective_threshold
                ELSE false
            END AS is_breach
        FROM metric_values m
        INNER JOIN applicable_rules r
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
            comparison,
            configured_threshold,
            baseline_percentile,
            effective_threshold,
            baseline_average,
            baseline_p90,
            baseline_p95,
            baseline_sample_count,
            historical_years,
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
        CASE
            WHEN comparison = 'baseline_percentile' THEN concat(
                rule_id, ': ', metric, ' remained ', operator_label, ' the local ', baseline_percentile,
                ' baseline of ', round(effective_threshold, 1), ' for ', observed_persistence_hours,
                ' consecutive forecast hours in ', city_id, '.'
            )
            ELSE concat(
                rule_id, ': ', metric, ' remained ', operator_label, ' ', effective_threshold,
                ' for ', observed_persistence_hours, ' consecutive forecast hours in ', city_id, '.'
            )
        END AS trigger_explanation
    FROM qualifying_streaks
) TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD);
