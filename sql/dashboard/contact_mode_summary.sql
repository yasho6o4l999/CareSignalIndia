SELECT preferred_channel AS contact_mode, count(DISTINCT member_id) AS contactable_members
FROM read_parquet('{member_risk_exposure_path}')
WHERE decision_date = ?
  AND outreach_eligible
  AND (? IS NULL OR city_id = ?)
GROUP BY preferred_channel
ORDER BY contactable_members DESC;
