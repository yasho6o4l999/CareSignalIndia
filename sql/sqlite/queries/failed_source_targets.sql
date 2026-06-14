SELECT source, city_id, error_message
FROM source_pipeline_state
WHERE run_id = ? AND status = 'failed'
ORDER BY source, city_id;
