PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    published_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'partial_success', 'failed')),
    records_extracted INTEGER NOT NULL DEFAULT 0,
    records_valid INTEGER NOT NULL DEFAULT 0,
    records_invalid INTEGER NOT NULL DEFAULT 0,
    records_published INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    ruleset_version TEXT,
    member_generator_version TEXT,
    baseline_end_year INTEGER
);

CREATE TABLE IF NOT EXISTS source_readiness (
    run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    source TEXT NOT NULL,
    city_id TEXT NOT NULL,
    status TEXT NOT NULL,
    extraction_started_at TEXT,
    extraction_completed_at TEXT,
    records_received INTEGER NOT NULL DEFAULT 0,
    records_valid INTEGER NOT NULL DEFAULT 0,
    records_invalid INTEGER NOT NULL DEFAULT 0,
    latest_source_timestamp TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    PRIMARY KEY (run_id, source, city_id)
);

CREATE TABLE IF NOT EXISTS pipeline_watermarks (
    source TEXT NOT NULL,
    city_id TEXT NOT NULL,
    watermark_type TEXT NOT NULL,
    watermark_value TEXT NOT NULL,
    updated_by_run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (source, city_id, watermark_type)
);

CREATE TABLE IF NOT EXISTS invalid_records (
    invalid_record_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    source TEXT NOT NULL,
    city_id TEXT,
    error_type TEXT NOT NULL,
    field_name TEXT,
    error_message TEXT NOT NULL,
    record_payload TEXT NOT NULL,
    quarantined_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS published_datasets (
    run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    dataset_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    minimum_timestamp TEXT,
    maximum_timestamp TEXT,
    published_at TEXT NOT NULL,
    PRIMARY KEY (run_id, dataset_name)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status_published ON pipeline_runs(status, published_at);
CREATE INDEX IF NOT EXISTS idx_source_readiness_run_status ON source_readiness(run_id, status);
CREATE INDEX IF NOT EXISTS idx_invalid_records_run_source ON invalid_records(run_id, source);

