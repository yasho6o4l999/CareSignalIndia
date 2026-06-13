SELECT
    count(*) AS row_count,
    count(DISTINCT city_id) AS city_count,
    count(DISTINCT year(observed_date)) AS year_count,
    max(observed_date) AS latest_observed_date
FROM read_parquet('{dataset_path}', hive_partitioning = true);

