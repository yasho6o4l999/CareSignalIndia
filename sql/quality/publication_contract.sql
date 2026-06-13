SELECT
    (SELECT count(*) FROM read_parquet('{outreach_queue_path}') WHERE outreach_consent = false) AS consent_leakage,
    (
        SELECT count(*)
        FROM (
            SELECT member_id, rule_id, window_start, count(*) AS duplicate_count
            FROM read_parquet('{outreach_queue_path}')
            GROUP BY member_id, rule_id, window_start
            HAVING count(*) > 1
        )
    ) AS duplicate_member_triggers,
    (
        SELECT count(*)
        FROM read_parquet('{active_triggers_path}')
        WHERE observed_persistence_hours < persistence_hours
    ) AS invalid_persistence_windows;

