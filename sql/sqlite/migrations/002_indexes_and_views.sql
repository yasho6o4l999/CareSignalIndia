CREATE INDEX IF NOT EXISTS idx_operational_run_status_published
ON operational_run(status, published_at DESC);

CREATE INDEX IF NOT EXISTS idx_source_state_current
ON source_pipeline_state(
    source, city_id, watermark_type, status, watermark_advanced,
    extraction_completed_at DESC, run_id DESC
);

CREATE INDEX IF NOT EXISTS idx_source_state_run_status
ON source_pipeline_state(run_id, status);

CREATE INDEX IF NOT EXISTS idx_pipeline_stage_execution_run
ON pipeline_stage_execution(run_id, started_at);

CREATE INDEX IF NOT EXISTS idx_artifact_run_type
ON data_artifact(run_id, artifact_type, dataset_name);

CREATE INDEX IF NOT EXISTS idx_artifact_source_city
ON data_artifact(source, city_id, published_at DESC);

CREATE INDEX IF NOT EXISTS idx_validation_issue_run_source
ON validation_issue(run_id, source, severity);

CREATE INDEX IF NOT EXISTS idx_quality_result_run_status
ON quality_check_result(run_id, status);

CREATE INDEX IF NOT EXISTS idx_quality_profile_history
ON quality_profile(stage, dataset, metric_name, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_dim_member_active_city
ON dim_member(is_active, city_id);

CREATE INDEX IF NOT EXISTS idx_member_condition_condition
ON bridge_member_condition(condition);

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
