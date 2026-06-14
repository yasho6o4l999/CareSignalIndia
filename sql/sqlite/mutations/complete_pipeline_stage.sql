UPDATE pipeline_stage_execution
SET completed_at = ?, status = ?, duration_ms = ?, output_records = ?, error_message = ?
WHERE run_id = ? AND stage_name = ?;
