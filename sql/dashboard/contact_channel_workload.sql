SELECT
    preferred_channel AS contact_channel,
    count(DISTINCT member_id) AS contactable_members,
    count(DISTINCT member_id) FILTER (WHERE priority_score >= 4) AS high_priority_members
FROM read_parquet('{member_risk_exposure_path}')
WHERE decision_date = ?
  AND outreach_eligible
GROUP BY preferred_channel
ORDER BY contactable_members DESC;
