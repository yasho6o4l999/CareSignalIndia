INSERT INTO invalid_records(
    run_id, source, city_id, error_type, field_name, error_message, record_payload, quarantined_at,
    natural_key, invalid_value, severity, validation_version
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
