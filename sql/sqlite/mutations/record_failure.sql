INSERT OR REPLACE INTO source_readiness(
    run_id, source, city_id, status, extraction_completed_at, records_invalid, records_rejected, error_message
)
VALUES (?, ?, ?, 'failed', ?, 1, 1, ?);
