INSERT OR REPLACE INTO reference_snapshot(
    snapshot_id, snapshot_type, generator_version, configuration_version, manifest_path,
    manifest_checksum, primary_record_count, related_record_count, created_at, status
)
VALUES (?, 'member', ?, ?, ?, ?, ?, ?, ?, 'published');
