UPDATE pipeline_runs
SET completed_at = ?,
    published_at = CASE WHEN ? IN ('success', 'partial_success') THEN ? ELSE published_at END,
    status = ?,
    records_extracted = ?,
    records_valid = ?,
    records_invalid = ?,
    records_published = ?,
    error_message = ?
WHERE run_id = ?;
