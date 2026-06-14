SELECT run_id, file_path, manifest_path, content_hash, file_checksum, row_count,
       minimum_timestamp, maximum_timestamp
FROM raw_manifests
WHERE source = ? AND city_id = ?
ORDER BY published_at DESC
LIMIT 1;
