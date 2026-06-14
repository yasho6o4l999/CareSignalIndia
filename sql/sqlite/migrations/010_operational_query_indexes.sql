DROP INDEX IF EXISTS idx_source_state_latest_success;

CREATE INDEX IF NOT EXISTS idx_source_state_current
ON source_pipeline_state(
    source, city_id, watermark_type, status, watermark_advanced,
    extraction_completed_at DESC, run_id DESC
);
