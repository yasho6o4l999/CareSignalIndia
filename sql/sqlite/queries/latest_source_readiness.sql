SELECT source, city_id, status, records_received, records_valid, records_invalid,
       latest_source_timestamp, retry_count, error_message
FROM source_readiness
WHERE run_id = ?
ORDER BY source, city_id;

