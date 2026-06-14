INSERT OR REPLACE INTO pipeline_stage_execution(
    run_id, stage_name, started_at, status, input_records
) VALUES (?, ?, ?, 'running', ?);
