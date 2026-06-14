SELECT artifact_id
FROM data_artifact
WHERE run_id = ?
  AND source = ?
  AND artifact_type = 'city_snapshot'
ORDER BY city_id;
