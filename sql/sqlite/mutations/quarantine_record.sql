INSERT INTO invalid_records(
    run_id, source, city_id, error_type, error_message, record_payload, quarantined_at
)
VALUES (?, ?, ?, ?, ?, ?, ?);
