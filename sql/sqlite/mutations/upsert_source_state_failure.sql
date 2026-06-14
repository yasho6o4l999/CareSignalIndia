INSERT INTO source_pipeline_state(
    run_id, source, city_id, status, extraction_completed_at, attempts, duration_ms,
    http_status, response_bytes, records_invalid, records_rejected, error_message
)
SELECT
    ?, ?, ?, 'failed', ?, coalesce(e.attempts, 0), coalesce(e.duration_ms, 0),
    e.http_status, coalesce(e.response_bytes, 0), 1, 1, ?
FROM (SELECT 1) seed
LEFT JOIN extraction_metrics e
    ON e.run_id = ? AND e.source = ? AND e.city_id = ?
ON CONFLICT(run_id, source, city_id) DO UPDATE SET
    status = 'failed',
    extraction_completed_at = excluded.extraction_completed_at,
    attempts = excluded.attempts,
    duration_ms = excluded.duration_ms,
    http_status = excluded.http_status,
    response_bytes = excluded.response_bytes,
    records_invalid = excluded.records_invalid,
    records_rejected = excluded.records_rejected,
    error_message = excluded.error_message;
