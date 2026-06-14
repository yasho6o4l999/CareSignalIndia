INSERT INTO source_pipeline_state(
    run_id, source, city_id, status, extraction_started_at, extraction_completed_at,
    attempts, duration_ms, http_status, response_bytes, records_received, records_valid,
    records_invalid, records_inserted, records_updated, records_unchanged, records_rejected,
    latest_source_timestamp
)
SELECT
    ?, ?, ?, 'success', ?, ?, coalesce(e.attempts, 0), coalesce(e.duration_ms, 0),
    e.http_status, coalesce(e.response_bytes, 0), ?, ?, ?, ?, ?, ?, ?, ?
FROM (SELECT 1) seed
LEFT JOIN extraction_metrics e
    ON e.run_id = ? AND e.source = ? AND e.city_id = ?
ON CONFLICT(run_id, source, city_id) DO UPDATE SET
    status = 'success',
    extraction_started_at = excluded.extraction_started_at,
    extraction_completed_at = excluded.extraction_completed_at,
    attempts = excluded.attempts,
    duration_ms = excluded.duration_ms,
    http_status = excluded.http_status,
    response_bytes = excluded.response_bytes,
    records_received = excluded.records_received,
    records_valid = excluded.records_valid,
    records_invalid = excluded.records_invalid,
    records_inserted = excluded.records_inserted,
    records_updated = excluded.records_updated,
    records_unchanged = excluded.records_unchanged,
    records_rejected = excluded.records_rejected,
    latest_source_timestamp = excluded.latest_source_timestamp,
    error_message = NULL;
