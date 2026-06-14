CREATE TABLE IF NOT EXISTS quality_profile (
    run_id TEXT NOT NULL REFERENCES operational_run(run_id) ON DELETE CASCADE,
    stage TEXT NOT NULL CHECK (stage IN ('source', 'staging', 'mart')),
    dataset TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (run_id, stage, dataset, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_quality_profile_history
ON quality_profile(stage, dataset, metric_name, recorded_at DESC);
