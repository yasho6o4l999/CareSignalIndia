SELECT run_id, started_at, completed_at, published_at, status,
       records_extracted, records_valid, records_invalid, records_published,
       records_inserted, records_updated, records_unchanged, records_rejected, error_message
FROM pipeline_runs
ORDER BY started_at DESC
LIMIT ?;
