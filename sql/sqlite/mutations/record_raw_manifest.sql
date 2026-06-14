INSERT OR REPLACE INTO raw_manifests(
    run_id, source, city_id, file_path, manifest_path, content_hash, file_checksum, row_count,
    minimum_timestamp, maximum_timestamp, reused_from_run_id, published_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
