WITH approved_cities AS (
    SELECT DISTINCT city_id FROM read_parquet('{publication_cities_path}')
),
outreach AS (
    SELECT * FROM read_parquet('{outreach_queue_path}')
),
triggers AS (
    SELECT * FROM read_parquet('{active_triggers_path}')
),
alerts AS (
    SELECT * FROM read_parquet('{stakeholder_alerts_path}')
),
expected_alerts AS (
    SELECT
        ruleset_version, rule_id, city_id, window_start,
        count(DISTINCT member_id) AS eligible_members,
        count(DISTINCT member_id) FILTER (WHERE priority_score >= 4) AS high_priority_members
    FROM outreach
    GROUP BY ruleset_version, rule_id, city_id, window_start
)
SELECT
    (SELECT count(*) FROM outreach WHERE outreach_consent = false) AS consent_leakage,
    (
        SELECT count(*) FROM (
            SELECT member_id, rule_id, window_start
            FROM outreach
            GROUP BY member_id, rule_id, window_start
            HAVING count(*) > 1
        )
    ) AS duplicate_member_triggers,
    (
        SELECT count(*) FROM triggers
        WHERE observed_persistence_hours < persistence_hours
    ) AS invalid_persistence_windows,
    (
        SELECT count(*) FROM outreach o
        ANTI JOIN triggers t
            ON o.ruleset_version = t.ruleset_version
           AND o.rule_id = t.rule_id
           AND o.city_id = t.city_id
           AND o.window_start = t.window_start
    ) AS orphan_outreach_triggers,
    (
        SELECT count(*) FROM expected_alerts e
        FULL OUTER JOIN alerts a
            ON e.ruleset_version = a.ruleset_version
           AND e.rule_id = a.rule_id
           AND e.city_id = a.city_id
           AND e.window_start = a.window_start
        WHERE e.eligible_members IS DISTINCT FROM a.eligible_members
           OR e.high_priority_members IS DISTINCT FROM a.high_priority_members
    ) AS stakeholder_reconciliation_errors,
    (
        SELECT count(*) FROM (
            SELECT city_id FROM triggers
            UNION ALL SELECT city_id FROM outreach
            UNION ALL SELECT city_id FROM alerts
        ) records
        ANTI JOIN approved_cities USING (city_id)
    ) AS unapproved_city_records;
