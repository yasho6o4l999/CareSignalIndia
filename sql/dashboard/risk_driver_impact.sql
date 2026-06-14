SELECT
    signal_name AS environmental_condition,
    count(DISTINCT member_id) AS at_risk_members,
    count(DISTINCT member_id) FILTER (WHERE outreach_eligible) AS contactable_members,
    count(DISTINCT city_id) AS affected_cities,
    max(severity_rank) AS maximum_severity_rank
FROM read_parquet('{member_risk_exposure_path}')
WHERE decision_date = ?
GROUP BY signal_name
ORDER BY at_risk_members DESC, maximum_severity_rank DESC;
