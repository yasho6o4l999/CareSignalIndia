SELECT artifact_id
FROM data_artifact
WHERE run_id = ?
  AND artifact_type = 'compacted_source_snapshot'
UNION
SELECT a.artifact_id
FROM data_artifact a
INNER JOIN operational_run r
    ON r.run_id = ?
   AND a.artifact_type = 'reference_snapshot'
   AND a.dataset_name = r.member_snapshot_id;
