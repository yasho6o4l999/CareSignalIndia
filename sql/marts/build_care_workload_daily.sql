COPY (
    WITH member_totals AS (
        SELECT city_id, count(DISTINCT member_id) AS total_members
        FROM read_parquet('{members_path}') m
        INNER JOIN (
            SELECT DISTINCT city_id FROM read_parquet('{publication_cities_path}')
        ) publication_cities USING (city_id)
        GROUP BY city_id
    ),
    date_city_spine AS (
        SELECT DISTINCT decision_date, city_id
        FROM read_parquet('{environmental_metrics_daily_path}')
    ),
    exposure AS (
        SELECT
            decision_date,
            city_id,
            count(DISTINCT member_id) AS at_risk_members,
            count(DISTINCT member_id) FILTER (WHERE outreach_eligible) AS contactable_members,
            count(DISTINCT member_id) FILTER (WHERE priority_score >= 4) AS high_priority_members,
            count(DISTINCT rule_id) AS active_conditions,
            max(severity_rank) AS maximum_severity_rank
        FROM read_parquet('{member_risk_exposure_daily_path}')
        GROUP BY decision_date, city_id
    )
    SELECT
        s.decision_date,
        s.city_id,
        coalesce(e.at_risk_members, 0) AS at_risk_members,
        coalesce(e.contactable_members, 0) AS contactable_members,
        coalesce(e.high_priority_members, 0) AS high_priority_members,
        coalesce(e.active_conditions, 0) AS active_conditions,
        coalesce(e.maximum_severity_rank, 0) AS maximum_severity_rank,
        t.total_members,
        round(100.0 * coalesce(e.at_risk_members, 0) / nullif(t.total_members, 0), 2)
            AS at_risk_percentage
    FROM date_city_spine s
    INNER JOIN member_totals t USING (city_id)
    LEFT JOIN exposure e USING (decision_date, city_id)
) TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD);
