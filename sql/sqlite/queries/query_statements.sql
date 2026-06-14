-- name: all_member_conditions
SELECT member_id, condition
FROM bridge_member_condition
ORDER BY member_id, condition;

-- name: applied_migrations
SELECT version FROM schema_migrations;

-- name: current_member_conditions
SELECT member_id, condition
FROM bridge_member_condition c
INNER JOIN dim_member m USING (member_id)
WHERE m.is_active = 1
ORDER BY member_id, condition;

-- name: current_members
SELECT m.member_id, m.city_id, m.age_band, m.preferred_language, m.preferred_channel,
       m.outreach_consent, m.generator_version
FROM dim_member m
WHERE m.is_active = 1
GROUP BY m.member_id, m.city_id, m.age_band, m.preferred_language, m.preferred_channel,
         m.outreach_consent, m.generator_version
ORDER BY member_id;

-- name: current_source_watermark
SELECT resulting_watermark_value AS watermark_value
FROM source_pipeline_state
WHERE source = ?
  AND city_id = ?
  AND watermark_type = ?
  AND status = 'success'
  AND watermark_advanced = 1
ORDER BY extraction_completed_at DESC, run_id DESC
LIMIT 1;

-- name: failed_source_targets
SELECT source, city_id, error_message
FROM source_pipeline_state
WHERE run_id = ? AND status = 'failed'
ORDER BY source, city_id;

-- name: latest_invalid_counts
SELECT
    source,
    severity,
    count(DISTINCT coalesce(city_id, '') || ':' || coalesce(natural_key, record_payload))
        AS invalid_records
FROM validation_issue
WHERE run_id = ?
GROUP BY source, severity
ORDER BY source, severity;

-- name: latest_member_snapshot
SELECT snapshot_id
FROM reference_snapshot
WHERE snapshot_type = 'member'
  AND status = 'published'
ORDER BY created_at DESC
LIMIT 1;

-- name: latest_pipeline_stages
SELECT stage_name, status, duration_ms, input_records, output_records, error_message
FROM pipeline_stage_execution
WHERE run_id = ?
ORDER BY started_at;

-- name: latest_published_run
SELECT r.run_id, r.status, r.published_at, m.records_published, r.ruleset_version, r.member_generator_version,
       baseline_end_year, configuration_version, member_snapshot_id
FROM operational_run r
INNER JOIN operational_run_metric m USING (run_id)
WHERE r.status IN ('success', 'partial_success')
  AND r.published_at IS NOT NULL
ORDER BY r.published_at DESC
LIMIT 1;

-- name: latest_quality_results
SELECT check_name, dataset, status, details, checked_at
FROM quality_check_result
WHERE run_id = ?
ORDER BY status DESC, dataset, check_name;

-- name: latest_raw_manifest
SELECT run_id, file_path, manifest_path, content_hash, file_checksum, record_count AS row_count,
       minimum_timestamp, maximum_timestamp, artifact_type, schema_version, schema_fingerprint,
       file_size_bytes, row_group_count, input_file_count
FROM data_artifact
WHERE source = ? AND city_id = ?
ORDER BY published_at DESC
LIMIT 1;

-- name: latest_source_readiness
SELECT source, city_id, status, records_received, records_valid, records_invalid,
       records_inserted, records_updated, records_unchanged, records_rejected,
       latest_source_timestamp, attempts, error_message
FROM source_pipeline_state
WHERE run_id = ?
ORDER BY source, city_id;

-- name: member_state
SELECT member_id, city_id, age_band, preferred_language, preferred_channel, outreach_consent,
       generator_version, source_hash, is_active
FROM dim_member
ORDER BY member_id;

-- name: previous_quality_profiles
SELECT p.dataset, p.metric_name, avg(p.metric_value) AS average_value, count(*) AS sample_count
FROM quality_profile p
INNER JOIN operational_run r USING (run_id)
WHERE p.stage = ?
  AND p.run_id <> ?
  AND r.status IN ('success', 'partial_success')
GROUP BY p.dataset, p.metric_name;

-- name: protected_member_snapshots
SELECT DISTINCT member_snapshot_id
FROM operational_run
WHERE status IN ('success', 'partial_success')
  AND member_snapshot_id IS NOT NULL;

-- name: run_upstream_artifacts
SELECT artifact_id
FROM data_artifact
WHERE run_id = ?
  AND artifact_type = 'compacted_source_snapshot'
UNION
SELECT a.artifact_id
FROM data_artifact a
INNER JOIN operational_run r
    ON r.run_id = ?
   AND a.artifact_type = 'reference_snapshot'
   AND a.dataset_name = r.member_snapshot_id;

-- name: source_run_city_artifacts
SELECT artifact_id
FROM data_artifact
WHERE run_id = ?
  AND source = ?
  AND artifact_type = 'city_snapshot'
ORDER BY city_id;
