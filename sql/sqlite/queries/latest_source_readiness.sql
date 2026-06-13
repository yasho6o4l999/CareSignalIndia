SELECT source, city_id, status, records_received, records_valid, records_invalid,
       records_inserted, records_updated, records_unchanged, records_rejected,
       latest_source_timestamp, retry_count, error_message
FROM source_readiness
WHERE run_id = ?
ORDER BY source, city_id;
