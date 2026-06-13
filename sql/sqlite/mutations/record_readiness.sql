INSERT OR REPLACE INTO source_readiness(
    run_id, source, city_id, status, extraction_started_at, extraction_completed_at,
    records_received, records_valid, records_invalid, records_inserted, records_updated,
    records_unchanged, records_rejected, latest_source_timestamp
)
VALUES (?, ?, ?, 'success', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
