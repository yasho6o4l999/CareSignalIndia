COPY (
    WITH metric_values AS (
        SELECT city_id, observed_at, metric, metric_value
        FROM read_parquet('{city_conditions_path}')
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
                ('pm2_5_rolling_24h', pm2_5_rolling_24h)
        ) metrics(metric, metric_value)
    ),
    applicable_predicates AS (
        SELECT
            d.*,
            p.predicate_index,
            p.metric,
            p.operator,
            p.operator_label,
            p.comparison,
            p.threshold AS configured_threshold,
            p.baseline_percentile,
            CASE
                WHEN p.comparison = 'absolute' THEN p.threshold
                WHEN p.baseline_percentile = 'p10' THEN b.p10_value
                WHEN p.baseline_percentile = 'p90' THEN b.p90_value
                WHEN p.baseline_percentile = 'p95' THEN b.p95_value
            END AS effective_threshold,
            b.average_value AS baseline_average,
            b.p10_value AS baseline_p10,
            b.p90_value AS baseline_p90,
            b.p95_value AS baseline_p95,
            b.sample_count AS baseline_sample_count,
            b.historical_years
        FROM read_parquet('{rules_path}') d
        INNER JOIN read_parquet('{rule_predicates_path}') p USING (ruleset_version, rule_id)
        LEFT JOIN read_parquet('{historical_baselines_path}') b
            ON d.city_id = b.city_id
           AND d.month = b.month
           AND p.metric = b.metric
        WHERE p.comparison = 'absolute' OR b.city_id IS NOT NULL
    ),
    predicate_evaluations AS (
        SELECT
            p.*,
            m.observed_at,
            m.metric_value,
            CASE
                WHEN p.operator = 'greater_than_or_equal' THEN m.metric_value >= p.effective_threshold
                WHEN p.operator = 'less_than_or_equal' THEN m.metric_value <= p.effective_threshold
                ELSE false
            END AS predicate_satisfied,
            CASE
                WHEN p.operator = 'greater_than_or_equal'
                    THEN 1 + ((m.metric_value - p.effective_threshold) / greatest(abs(p.effective_threshold), 1))
                WHEN p.operator = 'less_than_or_equal'
                    THEN 1 + ((p.effective_threshold - m.metric_value) / greatest(abs(p.effective_threshold), 1))
            END AS threshold_ratio,
            concat(
                p.metric, ' ', p.operator_label, ' ',
                CASE
                    WHEN p.comparison = 'baseline_percentile'
                        THEN concat('local ', p.baseline_percentile, ' ', round(p.effective_threshold, 1))
                    ELSE CAST(round(p.effective_threshold, 1) AS VARCHAR)
                END
            ) AS predicate_explanation
        FROM metric_values m
        INNER JOIN applicable_predicates p
            ON m.city_id = p.city_id
           AND m.metric = p.metric
           AND month(m.observed_at) = p.month
    ),
    rule_evaluations AS (
        SELECT
            ruleset_version,
            rule_id,
            city_id,
            month,
            condition_logic,
            max(predicate_count) AS predicate_count,
            persistence_hours,
            severity,
            signal_name,
            signal_category,
            observed_at,
            count(*) FILTER (WHERE predicate_satisfied) = max(predicate_count) AS is_breach,
            min(threshold_ratio) AS threshold_ratio,
            string_agg(predicate_explanation, ' AND ' ORDER BY predicate_index) AS predicate_explanation,
            list(metric ORDER BY predicate_index) AS metrics,
            list(metric_value ORDER BY predicate_index) AS metric_values,
            list(effective_threshold ORDER BY predicate_index) AS effective_thresholds
        FROM predicate_evaluations
        GROUP BY ruleset_version, rule_id, city_id, month, condition_logic,
                 persistence_hours, severity, signal_name, signal_category, observed_at
        HAVING count(*) = max(predicate_count)
    ),
    with_previous AS (
        SELECT
            *,
            lag(observed_at) OVER (
                PARTITION BY ruleset_version, rule_id, city_id
                ORDER BY observed_at
            ) AS previous_observed_at
        FROM rule_evaluations
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
        FROM with_previous
    )
    , persisted_windows AS (
        SELECT
            ruleset_version,
            rule_id,
            city_id,
            signal_name,
            signal_category,
            predicate_count,
            persistence_hours,
            streak_group,
            min(observed_at) AS window_start,
            max(observed_at) AS window_end,
            count(*) AS observed_persistence_hours,
            min(threshold_ratio) AS threshold_ratio,
            any_value(metrics) AS metrics,
            any_value(effective_thresholds) AS effective_thresholds,
            any_value(predicate_explanation) AS predicate_explanation
        FROM grouped
        WHERE is_breach
        GROUP BY ruleset_version, rule_id, city_id, signal_name, signal_category,
                 predicate_count, persistence_hours, streak_group
        HAVING count(*) >= persistence_hours
    ),
    qualified_severity AS (
        SELECT
            w.*,
            b.severity,
            b.severity_rank,
            row_number() OVER (
                PARTITION BY w.ruleset_version, w.rule_id, w.city_id, w.streak_group
                ORDER BY b.severity_rank DESC
            ) AS severity_choice
        FROM persisted_windows w
        INNER JOIN read_parquet('{rule_severity_bands_path}') b
            ON w.ruleset_version = b.ruleset_version
           AND w.rule_id = b.rule_id
           AND w.observed_persistence_hours >= b.minimum_persistence_hours
           AND w.threshold_ratio >= b.minimum_threshold_ratio
    )
    SELECT
        * EXCLUDE (severity_choice),
        CAST(timezone('{decision_timezone}', window_start) AS DATE) AS forecast_start_date,
        date_diff(
            'day',
            DATE '{decision_date}',
            CAST(timezone('{decision_timezone}', window_start) AS DATE)
        ) AS days_until_start,
        CASE
            WHEN CAST(timezone('{decision_timezone}', window_start) AS DATE) <= DATE '{decision_date}'
                THEN 'today_action'
            ELSE 'upcoming_risk'
        END AS action_timing,
        concat(
            signal_name, ': ', predicate_explanation, ' for ', observed_persistence_hours,
            ' consecutive forecast hours in ', city_id, '.'
        ) AS trigger_explanation
    FROM qualified_severity
    WHERE severity_choice = 1
) TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD);
