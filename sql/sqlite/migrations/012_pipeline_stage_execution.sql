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

CREATE INDEX IF NOT EXISTS idx_pipeline_stage_execution_run
ON pipeline_stage_execution(run_id, started_at);
