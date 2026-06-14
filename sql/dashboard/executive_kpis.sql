SELECT
    sum(total_members) AS total_members,
    sum(at_risk_members) AS at_risk_members,
    round(100.0 * sum(at_risk_members) / nullif(sum(total_members), 0), 2) AS at_risk_percentage,
    sum(contactable_members) AS contactable_members,
    sum(high_priority_members) AS high_priority_members,
    count(*) FILTER (WHERE at_risk_members > 0) AS affected_cities
FROM read_parquet('{care_workload_path}')
WHERE decision_date = ?
  AND (? IS NULL OR city_id = ?);
