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

INSERT OR IGNORE INTO operational_run
SELECT run_id, started_at, completed_at, published_at, status, error_message,
       configuration_version, ruleset_version, member_generator_version, member_snapshot_id,
       baseline_end_year
FROM pipeline_runs;

INSERT OR IGNORE INTO operational_run_metric
SELECT run_id, records_extracted, records_valid, records_invalid, records_published,
       records_inserted, records_updated, records_unchanged, records_rejected
FROM pipeline_runs;

INSERT OR IGNORE INTO source_pipeline_state(
    run_id, source, city_id, status, extraction_started_at, extraction_completed_at,
    attempts, duration_ms, http_status, response_bytes, records_received, records_valid,
    records_invalid, records_inserted, records_updated, records_unchanged, records_rejected,
    latest_source_timestamp, watermark_type, previous_watermark_value, resulting_watermark_value,
    watermark_advanced, error_message
)
SELECT
    r.run_id, r.source, r.city_id, r.status, r.extraction_started_at, r.extraction_completed_at,
    coalesce(e.attempts, r.retry_count), coalesce(e.duration_ms, 0), e.http_status,
    coalesce(e.response_bytes, 0), r.records_received, r.records_valid, r.records_invalid,
    r.records_inserted, r.records_updated, r.records_unchanged, r.records_rejected,
    r.latest_source_timestamp, w.watermark_type, NULL, w.watermark_value,
    CASE WHEN w.updated_by_run_id = r.run_id THEN 1 ELSE 0 END, r.error_message
FROM source_readiness r
LEFT JOIN extraction_metrics e USING (run_id, source, city_id)
LEFT JOIN pipeline_watermarks w
    ON r.source = w.source AND r.city_id = w.city_id AND w.updated_by_run_id = r.run_id;

INSERT OR IGNORE INTO data_artifact(
    artifact_id, run_id, artifact_type, dataset_name, source, city_id, file_path, manifest_path,
    content_hash, file_checksum, schema_version, schema_fingerprint, record_count, file_size_bytes,
    row_group_count, input_file_count, minimum_timestamp, maximum_timestamp, published_at
)
SELECT
    'raw:' || run_id || ':' || source || ':' || city_id, run_id, artifact_type, source, source,
    city_id, file_path, manifest_path, content_hash, file_checksum, schema_version,
    schema_fingerprint, row_count, file_size_bytes, row_group_count, input_file_count,
    minimum_timestamp, maximum_timestamp, published_at
FROM raw_manifests;

INSERT OR IGNORE INTO data_artifact(
    artifact_id, run_id, artifact_type, dataset_name, file_path, record_count,
    minimum_timestamp, maximum_timestamp, published_at
)
SELECT
    'processed:' || run_id || ':' || dataset_name, run_id, 'processed_dataset', dataset_name,
    file_path, record_count, minimum_timestamp, maximum_timestamp, published_at
FROM published_datasets;

INSERT OR IGNORE INTO data_artifact(
    artifact_id, artifact_type, dataset_name, file_path, manifest_path, file_checksum,
    record_count, published_at
)
SELECT
    'reference:member:' || snapshot_id, 'reference_snapshot', snapshot_id, manifest_path,
    manifest_path, manifest_checksum, member_count, created_at
FROM member_snapshots;

INSERT OR IGNORE INTO artifact_dependency(parent_artifact_id, child_artifact_id, relationship_type, created_at)
SELECT
    'raw:' || reused_from_run_id || ':' || source || ':' || city_id,
    'raw:' || run_id || ':' || source || ':' || city_id,
    'reused_from',
    published_at
FROM raw_manifests
WHERE reused_from_run_id IS NOT NULL;

INSERT OR IGNORE INTO artifact_dependency(parent_artifact_id, child_artifact_id, relationship_type, created_at)
SELECT
    parent.artifact_id,
    child.artifact_id,
    'derived_from',
    child.published_at
FROM data_artifact child
INNER JOIN operational_run run ON child.run_id = run.run_id
INNER JOIN data_artifact parent
    ON (
        parent.run_id = child.run_id
        AND parent.artifact_type = 'compacted_source_snapshot'
    ) OR (
        parent.artifact_type = 'reference_snapshot'
        AND parent.dataset_name = run.member_snapshot_id
    )
WHERE child.artifact_type = 'processed_dataset';

INSERT OR IGNORE INTO validation_issue(
    validation_issue_id, run_id, source, city_id, severity, natural_key, field_name, error_type,
    invalid_value, error_message, record_payload, validation_version, quarantined_at
)
SELECT invalid_record_id, run_id, source, city_id, severity, natural_key, field_name, error_type,
       invalid_value, error_message, record_payload, validation_version, quarantined_at
FROM invalid_records;

INSERT OR IGNORE INTO reference_snapshot
SELECT snapshot_id, 'member', generator_version, configuration_version, manifest_path,
       manifest_checksum, member_count, condition_count, created_at, status
FROM member_snapshots;

INSERT OR IGNORE INTO reference_sync_run
SELECT sync_id, 'member', started_at, completed_at, inserted, updated, deactivated, unchanged,
       condition_changes, changed_cities
FROM member_sync_runs;

CREATE INDEX IF NOT EXISTS idx_operational_run_status_published
ON operational_run(status, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_source_state_latest_success
ON source_pipeline_state(source, city_id, status, extraction_completed_at DESC);
CREATE INDEX IF NOT EXISTS idx_source_state_run_status
ON source_pipeline_state(run_id, status);
CREATE INDEX IF NOT EXISTS idx_artifact_run_type
ON data_artifact(run_id, artifact_type, dataset_name);
CREATE INDEX IF NOT EXISTS idx_artifact_source_city
ON data_artifact(source, city_id, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_validation_issue_run_source
ON validation_issue(run_id, source, severity);
CREATE INDEX IF NOT EXISTS idx_quality_result_run_status
ON quality_check_result(run_id, status);

CREATE VIEW IF NOT EXISTS current_source_state AS
WITH ranked AS (
    SELECT *,
           row_number() OVER (
               PARTITION BY source, city_id, watermark_type
               ORDER BY extraction_completed_at DESC, run_id DESC
           ) AS state_rank
    FROM source_pipeline_state
    WHERE status = 'success' AND watermark_advanced = 1
)
SELECT *
FROM ranked
WHERE state_rank = 1;

CREATE VIEW IF NOT EXISTS latest_run_source_health AS
SELECT s.*
FROM source_pipeline_state s
INNER JOIN (
    SELECT run_id
    FROM operational_run
    ORDER BY started_at DESC
    LIMIT 1
) latest USING (run_id);
