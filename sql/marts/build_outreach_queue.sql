COPY (
    WITH member_base AS (
        SELECT
            m.member_id,
            m.city_id,
            m.age_band,
            m.preferred_language,
            m.preferred_channel,
            m.outreach_consent,
            m.last_contact_date,
            c.condition
        FROM read_parquet('{members_path}') m
        INNER JOIN read_parquet('{member_conditions_path}') c USING (member_id)
        WHERE m.outreach_consent = true
          AND m.last_contact_date <= current_date - INTERVAL '{cooldown_hours} hours'
    ),
    eligible AS (
        SELECT
            m.*,
            t.ruleset_version,
            t.rule_id,
            t.signal_name,
            t.signal_category,
            t.severity,
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
            t.trigger_explanation,
            rc.relevance AS condition_relevance,
            CASE t.severity WHEN 'critical' THEN 4 WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END
                + CASE rc.relevance WHEN 'high' THEN 2 WHEN 'medium' THEN 1 ELSE 0 END
                + CASE WHEN m.age_band = '60+' THEN 1 ELSE 0 END AS priority_score
        FROM member_base m
        INNER JOIN read_parquet('{active_triggers_path}') t USING (city_id)
        INNER JOIN read_parquet('{rule_conditions_path}') rc
            ON t.ruleset_version = rc.ruleset_version
           AND t.rule_id = rc.rule_id
           AND m.condition = rc.condition
    )
    SELECT
        * EXCLUDE (condition, condition_relevance, priority_score),
        list_sort(list_distinct(list(condition))) AS matched_conditions,
        list_sort(list_distinct(list(condition_relevance))) AS matched_relevance_levels,
        max(priority_score) AS priority_score
    FROM eligible
    GROUP BY ALL
) TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD);
