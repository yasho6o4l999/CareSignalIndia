WITH scaled AS (
    SELECT
        exposure.*,
        scale_id
    FROM read_parquet('{member_risk_exposure_path}') exposure
    CROSS JOIN range({scale_factor}) scale(scale_id)
    WHERE decision_date = DATE '{decision_date}'
)
SELECT
    city_id,
    severity,
    count(*) AS exposure_rows,
    count(DISTINCT member_id || ':' || scale_id) AS members,
    count(*) FILTER (WHERE outreach_eligible) AS contactable_rows
FROM scaled
GROUP BY city_id, severity
ORDER BY exposure_rows DESC;
