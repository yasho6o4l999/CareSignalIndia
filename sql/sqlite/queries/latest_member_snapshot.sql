SELECT snapshot_id
FROM reference_snapshot
WHERE snapshot_type = 'member'
  AND status = 'published'
ORDER BY created_at DESC
LIMIT 1;
