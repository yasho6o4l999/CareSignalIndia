INSERT OR REPLACE INTO reference_sync_run(
    sync_id, reference_type, started_at, completed_at, inserted, updated, deactivated,
    unchanged, relationship_changes, changed_scopes
)
VALUES (?, 'member', ?, ?, ?, ?, ?, ?, ?, ?);
