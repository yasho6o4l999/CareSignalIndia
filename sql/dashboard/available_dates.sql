SELECT decision_date, max(run_id) AS latest_run_id
FROM read_parquet('{care_workload_history_path}', hive_partitioning = true)
GROUP BY decision_date
ORDER BY decision_date;
