INSERT OR REPLACE INTO extraction_metrics(
    run_id, source, city_id, duration_ms, attempts, http_status, response_bytes, status, recorded_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
