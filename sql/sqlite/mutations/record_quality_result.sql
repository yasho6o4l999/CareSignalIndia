INSERT OR REPLACE INTO quality_check_result(
    run_id, check_name, dataset, status, details, checked_at
)
VALUES (?, ?, ?, ?, ?, ?);
