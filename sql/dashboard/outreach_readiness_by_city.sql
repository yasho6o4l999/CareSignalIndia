SELECT
    city_id,
    at_risk_members,
    contactable_members,
    at_risk_members - contactable_members AS outreach_gap,
    round(100.0 * contactable_members / nullif(at_risk_members, 0), 1) AS contactable_percentage
FROM read_parquet('{care_workload_path}')
WHERE decision_date = ?
  AND at_risk_members > 0
ORDER BY at_risk_members DESC;
