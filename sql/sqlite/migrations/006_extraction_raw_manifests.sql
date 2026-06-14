CREATE TABLE IF NOT EXISTS extraction_metrics (
    run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    source TEXT NOT NULL,
    city_id TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    attempts INTEGER NOT NULL,
    http_status INTEGER,
    response_bytes INTEGER NOT NULL,
    status TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (run_id, source, city_id)
);

CREATE TABLE IF NOT EXISTS raw_manifests (
    run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    source TEXT NOT NULL,
    city_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    manifest_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    file_checksum TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    minimum_timestamp TEXT,
    maximum_timestamp TEXT,
    reused_from_run_id TEXT,
    published_at TEXT NOT NULL,
    PRIMARY KEY (run_id, source, city_id)
);

CREATE INDEX IF NOT EXISTS idx_raw_manifest_source_city ON raw_manifests(source, city_id, published_at);
