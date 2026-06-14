SELECT DISTINCT member_snapshot_id
FROM operational_run
WHERE status IN ('success', 'partial_success')
  AND member_snapshot_id IS NOT NULL;
