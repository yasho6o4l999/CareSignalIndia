UPDATE operational_run
SET completed_at = ?,
    published_at = CASE WHEN ? IN ('success', 'partial_success') THEN ? ELSE published_at END,
    status = ?,
    error_message = ?
WHERE run_id = ?;
