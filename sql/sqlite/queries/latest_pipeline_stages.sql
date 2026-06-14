SELECT stage_name, status, duration_ms, input_records, output_records, error_message
FROM pipeline_stage_execution
WHERE run_id = ?
ORDER BY started_at;
