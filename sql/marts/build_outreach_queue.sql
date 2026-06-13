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
    ),
    eligible AS (
        SELECT
            m.*,
            t.ruleset_version,
            t.rule_id,
            t.metric,
            t.severity,
            t.threshold,
            t.persistence_hours,
            t.observed_persistence_hours,
            t.window_start,
            t.window_end,
            t.minimum_metric_value,
            t.maximum_metric_value,
            t.trigger_explanation,
            CASE t.severity WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END
                + CASE WHEN m.age_band = '60+' THEN 1 ELSE 0 END AS priority_score
        FROM member_base m
        INNER JOIN read_parquet('{active_triggers_path}') t USING (city_id)
        INNER JOIN read_parquet('{rule_conditions_path}') rc
            ON t.ruleset_version = rc.ruleset_version
           AND t.rule_id = rc.rule_id
           AND m.condition = rc.condition
    )
    SELECT
        * EXCLUDE (condition),
        list_sort(list_distinct(list(condition))) AS matched_conditions
    FROM eligible
    GROUP BY ALL
) TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD);

