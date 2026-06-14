WITH expanded AS (
    SELECT
        member_id,
        outreach_eligible,
        priority_score,
        unnest(matched_conditions) AS member_condition
    FROM read_parquet('{member_risk_exposure_path}')
    WHERE decision_date = ?
)
SELECT
    member_condition,
    count(DISTINCT member_id) AS at_risk_members,
    count(DISTINCT member_id) FILTER (WHERE outreach_eligible) AS contactable_members,
    count(DISTINCT member_id) FILTER (WHERE priority_score >= 4) AS high_priority_members
FROM expanded
GROUP BY member_condition
ORDER BY at_risk_members DESC;
