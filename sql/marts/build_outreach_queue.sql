COPY (
    SELECT
        decision_date,
        member_id,
        city_id,
        age_band,
        preferred_language,
        preferred_channel,
        outreach_consent,
        ruleset_version,
        rule_id,
        signal_name,
        signal_category,
        severity,
        severity_rank,
        predicate_count,
        metrics,
        effective_thresholds,
        predicate_explanation,
        persistence_hours,
        observed_persistence_hours,
        window_start,
        window_end,
        forecast_start_date,
        days_until_start,
        action_timing,
        trigger_explanation,
        matched_conditions,
        matched_relevance_levels,
        priority_score
    FROM read_parquet('{member_risk_exposure_daily_path}')
    WHERE outreach_eligible
) TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD);
