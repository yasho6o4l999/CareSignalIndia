INSERT OR REPLACE INTO source_readiness(
    run_id, source, city_id, status, extraction_started_at, extraction_completed_at,
    records_received, records_valid, latest_source_timestamp
)
VALUES (?, ?, ?, 'success', ?, ?, ?, ?, ?);
