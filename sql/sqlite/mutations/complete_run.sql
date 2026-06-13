UPDATE pipeline_runs
SET completed_at = ?,
    published_at = CASE WHEN ? IN ('success', 'partial_success') THEN ? ELSE published_at END,
    status = ?,
    records_extracted = ?,
    records_valid = ?,
    records_invalid = ?,
    records_published = ?,
    records_inserted = ?,
    records_updated = ?,
    records_unchanged = ?,
    records_rejected = ?,
    error_message = ?
WHERE run_id = ?;
