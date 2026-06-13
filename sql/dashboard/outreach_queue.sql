SELECT
    member_id,
    city_id,
    matched_conditions,
    rule_id,
    severity,
    priority_score,
    preferred_channel,
    preferred_language,
    window_start,
    window_end,
    trigger_explanation
FROM read_parquet('{outreach_queue_path}')
WHERE (? IS NULL OR city_id = ?)
ORDER BY priority_score DESC
LIMIT 500;

