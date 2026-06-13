INSERT OR REPLACE INTO published_datasets(
    run_id, dataset_name, file_path, record_count, published_at
)
VALUES (?, ?, ?, ?, ?);
