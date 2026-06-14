SELECT p.dataset, p.metric_name, avg(p.metric_value) AS average_value, count(*) AS sample_count
FROM quality_profile p
INNER JOIN operational_run r USING (run_id)
WHERE p.stage = ?
  AND p.run_id <> ?
  AND r.status IN ('success', 'partial_success')
GROUP BY p.dataset, p.metric_name;
