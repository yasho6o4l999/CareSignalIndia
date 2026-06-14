SELECT source, city_id, severity, natural_key, field_name, error_type, invalid_value, error_message
FROM invalid_records
WHERE run_id = ?
ORDER BY source, city_id, severity, natural_key
LIMIT ?;
