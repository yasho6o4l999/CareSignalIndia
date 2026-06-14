INSERT INTO member_sync_runs(
    sync_id, started_at, completed_at, inserted, updated, deactivated, unchanged,
    condition_changes, changed_cities
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
