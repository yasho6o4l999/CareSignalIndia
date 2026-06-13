INSERT OR REPLACE INTO source_readiness(
    run_id, source, city_id, status, extraction_completed_at, records_invalid, error_message
)
VALUES (?, ?, ?, 'failed', ?, 1, ?);
