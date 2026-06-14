INSERT OR REPLACE INTO quality_profile(
    run_id, stage, dataset, metric_name, metric_value, recorded_at
)
VALUES (?, ?, ?, ?, ?, ?);
