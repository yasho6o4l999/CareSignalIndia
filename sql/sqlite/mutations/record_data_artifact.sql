INSERT OR REPLACE INTO data_artifact(
    artifact_id, run_id, artifact_type, dataset_name, source, city_id, file_path, manifest_path,
    content_hash, file_checksum, schema_version, schema_fingerprint, record_count, file_size_bytes,
    row_group_count, input_file_count, minimum_timestamp, maximum_timestamp, published_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
