-- name: record_artifact_dependency
INSERT OR IGNORE INTO artifact_dependency(
    parent_artifact_id, child_artifact_id, relationship_type, created_at
)
VALUES (?, ?, ?, ?);

-- name: record_data_artifact
INSERT OR REPLACE INTO data_artifact(
    artifact_id, run_id, artifact_type, dataset_name, source, city_id, file_path, manifest_path,
    content_hash, file_checksum, schema_version, schema_fingerprint, record_count, file_size_bytes,
    row_group_count, input_file_count, minimum_timestamp, maximum_timestamp, published_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);

-- name: record_extraction_request_metric
INSERT OR REPLACE INTO extraction_request_metric(
    run_id, source, city_id, duration_ms, attempts, http_status, response_bytes, status, recorded_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);

-- name: record_migration
INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?);

-- name: record_quality_profile
INSERT OR REPLACE INTO quality_profile(
    run_id, stage, dataset, metric_name, metric_value, recorded_at
)
VALUES (?, ?, ?, ?, ?, ?);

-- name: record_quality_result
INSERT OR REPLACE INTO quality_check_result(
    run_id, check_name, dataset, status, details, checked_at
)
VALUES (?, ?, ?, ?, ?, ?);

-- name: record_reference_sync
INSERT OR REPLACE INTO reference_sync_run(
    sync_id, reference_type, started_at, completed_at, inserted, updated, deactivated,
    unchanged, relationship_changes, changed_scopes
)
VALUES (?, 'member', ?, ?, ?, ?, ?, ?, ?, ?);

-- name: record_validation_issue
INSERT INTO validation_issue(
    run_id, source, city_id, severity, natural_key, field_name, error_type, invalid_value,
    error_message, record_payload, validation_version, quarantined_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);

-- name: register_reference_snapshot
INSERT OR REPLACE INTO reference_snapshot(
    snapshot_id, snapshot_type, generator_version, configuration_version, manifest_path,
    manifest_checksum, primary_record_count, related_record_count, created_at, status
)
VALUES (?, 'member', ?, ?, ?, ?, ?, ?, ?, 'published');

-- name: start_operational_run
INSERT INTO operational_run(
    run_id, started_at, status, ruleset_version, member_generator_version, baseline_end_year,
    configuration_version, member_snapshot_id
)
VALUES (?, ?, 'running', ?, ?, ?, ?, ?);

-- name: start_operational_run_metric
INSERT INTO operational_run_metric(run_id) VALUES (?);

-- name: start_pipeline_stage
INSERT OR REPLACE INTO pipeline_stage_execution(
    run_id, stage_name, started_at, status, input_records
) VALUES (?, ?, ?, 'running', ?);

-- name: insert_member_condition
INSERT INTO bridge_member_condition(member_id, condition) VALUES (?, ?);

-- name: upsert_member
INSERT INTO dim_member(
    member_id, city_id, age_band, preferred_language, preferred_channel, outreach_consent,
    generator_version, updated_at, source_hash, is_active
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
ON CONFLICT(member_id) DO UPDATE SET
    city_id = excluded.city_id,
    age_band = excluded.age_band,
    preferred_language = excluded.preferred_language,
    preferred_channel = excluded.preferred_channel,
    outreach_consent = excluded.outreach_consent,
    generator_version = excluded.generator_version,
    updated_at = excluded.updated_at,
    source_hash = excluded.source_hash,
    is_active = 1;

-- name: upsert_source_state_failure
INSERT INTO source_pipeline_state(
    run_id, source, city_id, status, extraction_completed_at, attempts, duration_ms,
    http_status, response_bytes, records_invalid, records_rejected, error_message
)
SELECT
    ?, ?, ?, 'failed', ?, coalesce(e.attempts, 0), coalesce(e.duration_ms, 0),
    e.http_status, coalesce(e.response_bytes, 0), 1, 1, ?
FROM (SELECT 1) seed
LEFT JOIN extraction_request_metric e
    ON e.run_id = ? AND e.source = ? AND e.city_id = ?
ON CONFLICT(run_id, source, city_id) DO UPDATE SET
    status = 'failed',
    extraction_completed_at = excluded.extraction_completed_at,
    attempts = excluded.attempts,
    duration_ms = excluded.duration_ms,
    http_status = excluded.http_status,
    response_bytes = excluded.response_bytes,
    records_invalid = excluded.records_invalid,
    records_rejected = excluded.records_rejected,
    error_message = excluded.error_message;

-- name: upsert_source_state_success
INSERT INTO source_pipeline_state(
    run_id, source, city_id, status, extraction_started_at, extraction_completed_at,
    attempts, duration_ms, http_status, response_bytes, records_received, records_valid,
    records_invalid, records_inserted, records_updated, records_unchanged, records_rejected,
    latest_source_timestamp
)
SELECT
    ?, ?, ?, 'success', ?, ?, coalesce(e.attempts, 0), coalesce(e.duration_ms, 0),
    e.http_status, coalesce(e.response_bytes, 0), ?, ?, ?, ?, ?, ?, ?, ?
FROM (SELECT 1) seed
LEFT JOIN extraction_request_metric e
    ON e.run_id = ? AND e.source = ? AND e.city_id = ?
ON CONFLICT(run_id, source, city_id) DO UPDATE SET
    status = 'success',
    extraction_started_at = excluded.extraction_started_at,
    extraction_completed_at = excluded.extraction_completed_at,
    attempts = excluded.attempts,
    duration_ms = excluded.duration_ms,
    http_status = excluded.http_status,
    response_bytes = excluded.response_bytes,
    records_received = excluded.records_received,
    records_valid = excluded.records_valid,
    records_invalid = excluded.records_invalid,
    records_inserted = excluded.records_inserted,
    records_updated = excluded.records_updated,
    records_unchanged = excluded.records_unchanged,
    records_rejected = excluded.records_rejected,
    latest_source_timestamp = excluded.latest_source_timestamp,
    error_message = NULL;
