SELECT
    member_id,
    city_id,
    matched_conditions,
    rule_id,
    severity,
    metrics,
    effective_thresholds,
    priority_score,
    preferred_channel,
    preferred_language,
    forecast_start_date,
    days_until_start,
    window_start,
    window_end,
    trigger_explanation
FROM read_parquet('{outreach_queue_path}')
WHERE action_timing = ?
  AND (? IS NULL OR city_id = ?)
ORDER BY days_until_start, priority_score DESC
LIMIT 500;
