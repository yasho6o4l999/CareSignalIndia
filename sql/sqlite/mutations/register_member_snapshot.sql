INSERT OR REPLACE INTO member_snapshots(
    snapshot_id, generator_version, configuration_version, manifest_path, manifest_checksum,
    member_count, condition_count, created_at, status
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'published');
