SELECT city_id, total_members, at_risk_members, at_risk_percentage, contactable_members,
       high_priority_members, active_conditions
FROM read_parquet('{care_workload_path}')
WHERE decision_date = ?
ORDER BY at_risk_percentage DESC, at_risk_members DESC;
