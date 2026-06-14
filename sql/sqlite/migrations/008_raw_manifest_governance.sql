ALTER TABLE raw_manifests ADD COLUMN artifact_type TEXT NOT NULL DEFAULT 'city_snapshot';
ALTER TABLE raw_manifests ADD COLUMN schema_version TEXT;
ALTER TABLE raw_manifests ADD COLUMN schema_fingerprint TEXT;
ALTER TABLE raw_manifests ADD COLUMN file_size_bytes INTEGER;
ALTER TABLE raw_manifests ADD COLUMN row_group_count INTEGER;
ALTER TABLE raw_manifests ADD COLUMN input_file_count INTEGER;

CREATE INDEX IF NOT EXISTS idx_raw_manifest_artifact
ON raw_manifests(run_id, source, artifact_type);
