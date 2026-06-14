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
    ),
    eligible AS (
        SELECT
            e.decision_date,
            m.*,
            e.ruleset_version,
            e.rule_id,
            e.signal_name,
            e.signal_category,
            e.severity,
            e.severity_rank,
            e.predicate_count,
            e.metrics,
            e.effective_thresholds,
            e.predicate_explanation,
            e.persistence_hours,
            e.observed_persistence_hours,
            e.window_start,
            e.window_end,
            e.forecast_start_date,
            e.days_until_start,
            e.action_timing,
            e.trigger_explanation,
            rc.relevance AS condition_relevance,
            CASE e.severity WHEN 'critical' THEN 4 WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END
                + CASE rc.relevance WHEN 'high' THEN 2 WHEN 'medium' THEN 1 ELSE 0 END
                + CASE WHEN m.age_band = '60+' THEN 1 ELSE 0 END AS priority_score
        FROM member_base m
        INNER JOIN read_parquet('{environmental_conditions_daily_path}') e USING (city_id)
        INNER JOIN read_parquet('{rule_conditions_path}') rc
            ON e.ruleset_version = rc.ruleset_version
           AND e.rule_id = rc.rule_id
           AND m.condition = rc.condition
    )
    SELECT
        * EXCLUDE (condition, condition_relevance, priority_score),
        list_sort(list_distinct(list(condition))) AS matched_conditions,
        list_sort(list_distinct(list(condition_relevance))) AS matched_relevance_levels,
        max(priority_score) AS priority_score,
        outreach_consent
            AND last_contact_date <= decision_date - INTERVAL '{cooldown_hours} hours'
            AS outreach_eligible,
        CASE
            WHEN NOT outreach_consent THEN 'no_outreach_consent'
            WHEN last_contact_date > decision_date - INTERVAL '{cooldown_hours} hours'
                THEN 'contact_cooldown'
            ELSE NULL
        END AS outreach_ineligibility_reason
    FROM eligible
    GROUP BY ALL
) TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD);
