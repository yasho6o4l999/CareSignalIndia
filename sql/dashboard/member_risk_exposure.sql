WITH city_impact AS (
    SELECT city_id, count(DISTINCT member_id) AS city_at_risk_members
    FROM read_parquet('{member_risk_exposure_path}')
    WHERE decision_date = ?
    GROUP BY city_id
)
SELECT
    e.member_id,
    e.city_id,
    e.signal_name AS environmental_condition,
    e.severity,
    e.priority_score,
    e.preferred_channel AS contact_mode,
    e.preferred_language,
    e.matched_conditions AS existing_conditions,
    e.metrics,
    e.effective_thresholds,
    e.outreach_eligible,
    e.outreach_ineligibility_reason,
    e.window_start,
    e.window_end,
    c.city_at_risk_members
FROM read_parquet('{member_risk_exposure_path}') e
INNER JOIN city_impact c USING (city_id)
WHERE e.decision_date = ?
  AND (? IS NULL OR e.city_id = ?)
  AND (? IS NULL OR e.severity = ?)
ORDER BY e.priority_score DESC, c.city_at_risk_members DESC, e.city_id, e.member_id
LIMIT 2000;
