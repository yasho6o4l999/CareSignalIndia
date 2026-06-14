INSERT OR IGNORE INTO artifact_dependency(
    parent_artifact_id, child_artifact_id, relationship_type, created_at
)
VALUES (?, ?, ?, ?);
