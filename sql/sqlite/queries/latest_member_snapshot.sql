SELECT snapshot_id
FROM member_snapshots
WHERE status = 'published'
ORDER BY created_at DESC
LIMIT 1;
