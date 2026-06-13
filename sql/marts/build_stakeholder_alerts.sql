COPY (
    SELECT
        ruleset_version,
        rule_id,
        signal_name,
        signal_category,
        city_id,
        severity,
        predicate_count,
        metrics,
        effective_thresholds,
        predicate_explanation,
        persistence_hours,
        observed_persistence_hours,
        window_start,
        window_end,
        trigger_explanation,
        count(DISTINCT member_id) AS eligible_members,
        count(DISTINCT member_id) FILTER (WHERE priority_score >= 4) AS high_priority_members
    FROM read_parquet('{outreach_queue_path}')
    GROUP BY ALL
) TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD);
