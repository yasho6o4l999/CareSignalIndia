SELECT run_id, status, published_at, records_published, ruleset_version, member_generator_version,
       baseline_end_year, configuration_version, member_snapshot_id
FROM pipeline_runs
WHERE status IN ('success', 'partial_success')
  AND published_at IS NOT NULL
ORDER BY published_at DESC
LIMIT 1;
