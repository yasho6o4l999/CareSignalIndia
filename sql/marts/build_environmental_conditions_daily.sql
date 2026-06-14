COPY (
    SELECT
        CAST(expanded.decision_date AS DATE) AS decision_date,
        t.ruleset_version,
        t.rule_id,
        t.signal_name,
        t.signal_category,
        t.city_id,
        t.severity,
        t.severity_rank,
        t.predicate_count,
        t.metrics,
        t.effective_thresholds,
        t.predicate_explanation,
        t.persistence_hours,
        t.observed_persistence_hours,
        t.window_start,
        t.window_end,
        t.forecast_start_date,
        t.days_until_start,
        t.action_timing,
        t.trigger_explanation
    FROM read_parquet('{active_triggers_path}') t
    CROSS JOIN LATERAL generate_series(
        t.forecast_start_date,
        CAST(timezone('{decision_timezone}', t.window_end) AS DATE),
        INTERVAL 1 DAY
    ) expanded(decision_date)
) TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD);
