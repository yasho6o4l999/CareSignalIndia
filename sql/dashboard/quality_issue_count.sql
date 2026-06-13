SELECT count(*)
FROM read_parquet('{quality_results_path}')
WHERE status <> 'pass';

