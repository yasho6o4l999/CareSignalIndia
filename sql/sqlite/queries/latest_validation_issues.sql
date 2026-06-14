SELECT source, city_id, severity, natural_key, field_name, error_type, invalid_value, error_message
FROM validation_issue
WHERE run_id = ?
ORDER BY source, city_id, severity, natural_key
LIMIT ?;
