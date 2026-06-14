SELECT r.run_id, r.started_at, r.completed_at, r.published_at, r.status,
       records_extracted, records_valid, records_invalid, records_published,
       records_inserted, records_updated, records_unchanged, records_rejected, r.error_message,
       r.ruleset_version, r.member_generator_version, r.baseline_end_year, r.configuration_version, r.member_snapshot_id
FROM operational_run r
INNER JOIN operational_run_metric m USING (run_id)
ORDER BY r.started_at DESC
LIMIT ?;
