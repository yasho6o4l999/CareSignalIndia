SELECT check_name, dataset, status, details, checked_at
FROM quality_check_result
WHERE run_id = ?
ORDER BY status DESC, dataset, check_name;
