-- name: advance_source_state_watermark
UPDATE source_pipeline_state
SET watermark_type = ?,
    previous_watermark_value = (
        SELECT resulting_watermark_value
        FROM current_source_state
        WHERE source = ? AND city_id = ? AND watermark_type = ?
    ),
    resulting_watermark_value = ?,
    watermark_advanced = 1
WHERE run_id = ? AND source = ? AND city_id = ? AND status = 'success';

-- name: complete_operational_run
UPDATE operational_run
SET completed_at = ?,
    published_at = CASE WHEN ? IN ('success', 'partial_success') THEN ? ELSE published_at END,
    status = ?,
    error_message = ?
WHERE run_id = ?;

-- name: complete_operational_run_metric
UPDATE operational_run_metric
SET records_extracted = ?,
    records_valid = ?,
    records_invalid = ?,
    records_published = ?,
    records_inserted = ?,
    records_updated = ?,
    records_unchanged = ?,
    records_rejected = ?
WHERE run_id = ?;

-- name: complete_pipeline_stage
UPDATE pipeline_stage_execution
SET completed_at = ?, status = ?, duration_ms = ?, output_records = ?, error_message = ?
WHERE run_id = ? AND stage_name = ?;

-- name: deactivate_member
UPDATE dim_member
SET is_active = 0, updated_at = ?
WHERE member_id = ?;

-- name: delete_member_conditions
DELETE FROM bridge_member_condition WHERE member_id = ?;

-- name: delete_reference_snapshot
DELETE FROM reference_snapshot WHERE snapshot_id = ? AND snapshot_type = 'member';
