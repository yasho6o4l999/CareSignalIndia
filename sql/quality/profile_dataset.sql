SELECT
    count(*) AS row_count,
    count(DISTINCT city_id || '|' || CAST(observed_at AS VARCHAR)) AS unique_natural_keys,
    max(observed_at) AS latest_observed_at
FROM read_parquet('{dataset_path}');

