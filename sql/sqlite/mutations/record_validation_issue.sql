INSERT INTO validation_issue(
    run_id, source, city_id, severity, natural_key, field_name, error_type, invalid_value,
    error_message, record_payload, validation_version, quarantined_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
