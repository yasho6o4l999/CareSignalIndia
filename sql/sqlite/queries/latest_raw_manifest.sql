SELECT run_id, file_path, manifest_path, content_hash, file_checksum, record_count AS row_count,
       minimum_timestamp, maximum_timestamp, artifact_type, schema_version, schema_fingerprint,
       file_size_bytes, row_group_count, input_file_count
FROM data_artifact
WHERE source = ? AND city_id = ?
ORDER BY published_at DESC
LIMIT 1;
