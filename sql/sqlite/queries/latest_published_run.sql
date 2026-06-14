SELECT r.run_id, r.status, r.published_at, m.records_published, r.ruleset_version, r.member_generator_version,
       baseline_end_year, configuration_version, member_snapshot_id
FROM operational_run r
INNER JOIN operational_run_metric m USING (run_id)
WHERE r.status IN ('success', 'partial_success')
  AND r.published_at IS NOT NULL
ORDER BY r.published_at DESC
LIMIT 1;
