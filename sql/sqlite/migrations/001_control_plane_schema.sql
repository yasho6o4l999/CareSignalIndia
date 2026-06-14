CREATE TABLE IF NOT EXISTS operational_run (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    published_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'partial_success', 'failed')),
    error_message TEXT,
    configuration_version TEXT,
    ruleset_version TEXT,
    member_generator_version TEXT,
    member_snapshot_id TEXT,
    baseline_end_year INTEGER
);

CREATE TABLE IF NOT EXISTS operational_run_metric (
    run_id TEXT PRIMARY KEY REFERENCES operational_run(run_id) ON DELETE CASCADE,
    records_extracted INTEGER NOT NULL DEFAULT 0 CHECK (records_extracted >= 0),
    records_valid INTEGER NOT NULL DEFAULT 0 CHECK (records_valid >= 0),
    records_invalid INTEGER NOT NULL DEFAULT 0 CHECK (records_invalid >= 0),
    records_published INTEGER NOT NULL DEFAULT 0 CHECK (records_published >= 0),
    records_inserted INTEGER NOT NULL DEFAULT 0 CHECK (records_inserted >= 0),
    records_updated INTEGER NOT NULL DEFAULT 0 CHECK (records_updated >= 0),
    records_unchanged INTEGER NOT NULL DEFAULT 0 CHECK (records_unchanged >= 0),
    records_rejected INTEGER NOT NULL DEFAULT 0 CHECK (records_rejected >= 0)
);

-- Request metrics arrive before readiness is known and are absorbed into source_pipeline_state.
CREATE TABLE IF NOT EXISTS extraction_request_metric (
    run_id TEXT NOT NULL REFERENCES operational_run(run_id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    city_id TEXT NOT NULL,
    duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0),
    attempts INTEGER NOT NULL CHECK (attempts >= 0),
    http_status INTEGER,
    response_bytes INTEGER NOT NULL CHECK (response_bytes >= 0),
    status TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (run_id, source, city_id)
);

CREATE TABLE IF NOT EXISTS source_pipeline_state (
    run_id TEXT NOT NULL REFERENCES operational_run(run_id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    city_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('success', 'failed')),
    extraction_started_at TEXT,
    extraction_completed_at TEXT,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    duration_ms INTEGER NOT NULL DEFAULT 0 CHECK (duration_ms >= 0),
    http_status INTEGER,
    response_bytes INTEGER NOT NULL DEFAULT 0 CHECK (response_bytes >= 0),
    records_received INTEGER NOT NULL DEFAULT 0 CHECK (records_received >= 0),
    records_valid INTEGER NOT NULL DEFAULT 0 CHECK (records_valid >= 0),
    records_invalid INTEGER NOT NULL DEFAULT 0 CHECK (records_invalid >= 0),
    records_inserted INTEGER NOT NULL DEFAULT 0 CHECK (records_inserted >= 0),
    records_updated INTEGER NOT NULL DEFAULT 0 CHECK (records_updated >= 0),
    records_unchanged INTEGER NOT NULL DEFAULT 0 CHECK (records_unchanged >= 0),
    records_rejected INTEGER NOT NULL DEFAULT 0 CHECK (records_rejected >= 0),
    latest_source_timestamp TEXT,
    watermark_type TEXT,
    previous_watermark_value TEXT,
    resulting_watermark_value TEXT,
    watermark_advanced INTEGER NOT NULL DEFAULT 0 CHECK (watermark_advanced IN (0, 1)),
    error_message TEXT,
    PRIMARY KEY (run_id, source, city_id)
);

CREATE TABLE IF NOT EXISTS pipeline_stage_execution (
    run_id TEXT NOT NULL REFERENCES operational_run(run_id) ON DELETE CASCADE,
    stage_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    duration_ms INTEGER NOT NULL DEFAULT 0 CHECK (duration_ms >= 0),
    input_records INTEGER NOT NULL DEFAULT 0 CHECK (input_records >= 0),
    output_records INTEGER NOT NULL DEFAULT 0 CHECK (output_records >= 0),
    error_message TEXT,
    PRIMARY KEY (run_id, stage_name)
);

CREATE TABLE IF NOT EXISTS data_artifact (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES operational_run(run_id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL CHECK (
        artifact_type IN ('city_snapshot', 'compacted_source_snapshot', 'processed_dataset', 'reference_snapshot')
    ),
    dataset_name TEXT NOT NULL,
    source TEXT,
    city_id TEXT,
    file_path TEXT NOT NULL,
    manifest_path TEXT,
    content_hash TEXT,
    file_checksum TEXT,
    schema_version TEXT,
    schema_fingerprint TEXT,
    record_count INTEGER NOT NULL DEFAULT 0 CHECK (record_count >= 0),
    file_size_bytes INTEGER,
    row_group_count INTEGER,
    input_file_count INTEGER,
    minimum_timestamp TEXT,
    maximum_timestamp TEXT,
    published_at TEXT NOT NULL,
    UNIQUE(run_id, artifact_type, dataset_name, city_id)
);

CREATE TABLE IF NOT EXISTS artifact_dependency (
    parent_artifact_id TEXT NOT NULL REFERENCES data_artifact(artifact_id) ON DELETE CASCADE,
    child_artifact_id TEXT NOT NULL REFERENCES data_artifact(artifact_id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL CHECK (
        relationship_type IN ('derived_from', 'reused_from', 'compacted_from')
    ),
    created_at TEXT NOT NULL,
    PRIMARY KEY (parent_artifact_id, child_artifact_id, relationship_type)
);

CREATE TABLE IF NOT EXISTS quality_check_result (
    run_id TEXT NOT NULL REFERENCES operational_run(run_id) ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    dataset TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pass', 'warning', 'fail')),
    details TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    PRIMARY KEY (run_id, check_name, dataset)
);

CREATE TABLE IF NOT EXISTS quality_profile (
    run_id TEXT NOT NULL REFERENCES operational_run(run_id) ON DELETE CASCADE,
    stage TEXT NOT NULL CHECK (stage IN ('source', 'staging', 'mart')),
    dataset TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (run_id, stage, dataset, metric_name)
);

CREATE TABLE IF NOT EXISTS validation_issue (
    validation_issue_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES operational_run(run_id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    city_id TEXT,
    severity TEXT NOT NULL CHECK (severity IN ('fatal', 'warning')),
    natural_key TEXT,
    field_name TEXT,
    error_type TEXT NOT NULL,
    invalid_value TEXT,
    error_message TEXT NOT NULL,
    record_payload TEXT NOT NULL,
    validation_version TEXT NOT NULL,
    quarantined_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_member (
    member_id TEXT PRIMARY KEY,
    city_id TEXT NOT NULL,
    age_band TEXT NOT NULL CHECK (age_band IN ('18-39', '40-59', '60+')),
    preferred_language TEXT NOT NULL,
    preferred_channel TEXT NOT NULL CHECK (preferred_channel IN ('app', 'sms', 'call')),
    outreach_consent INTEGER NOT NULL CHECK (outreach_consent IN (0, 1)),
    generator_version TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS bridge_member_condition (
    member_id TEXT NOT NULL REFERENCES dim_member(member_id) ON DELETE CASCADE,
    condition TEXT NOT NULL CHECK (condition IN ('diabetes', 'cardiovascular', 'renal', 'respiratory')),
    PRIMARY KEY (member_id, condition)
);

CREATE TABLE IF NOT EXISTS reference_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    snapshot_type TEXT NOT NULL,
    generator_version TEXT NOT NULL,
    configuration_version TEXT NOT NULL,
    manifest_path TEXT NOT NULL,
    manifest_checksum TEXT NOT NULL,
    primary_record_count INTEGER NOT NULL,
    related_record_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('published', 'invalid'))
);

CREATE TABLE IF NOT EXISTS reference_sync_run (
    sync_id TEXT PRIMARY KEY,
    reference_type TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    inserted INTEGER NOT NULL,
    updated INTEGER NOT NULL,
    deactivated INTEGER NOT NULL,
    unchanged INTEGER NOT NULL,
    relationship_changes INTEGER NOT NULL,
    changed_scopes TEXT NOT NULL
);
