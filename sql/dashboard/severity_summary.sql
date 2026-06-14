SELECT severity, count(DISTINCT member_id) AS at_risk_members
FROM read_parquet('{member_risk_exposure_path}')
WHERE decision_date = ?
  AND (? IS NULL OR city_id = ?)
GROUP BY severity, severity_rank
ORDER BY severity_rank DESC;
