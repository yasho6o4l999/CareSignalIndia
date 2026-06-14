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
