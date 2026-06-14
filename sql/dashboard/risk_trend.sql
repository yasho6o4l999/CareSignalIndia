WITH history AS (
    SELECT *
    FROM read_parquet('{care_workload_history_path}', hive_partitioning = true)
),
latest AS (
    SELECT decision_date, max(run_id) AS run_id
    FROM history
    GROUP BY decision_date
)
SELECT
    h.decision_date,
    sum(h.at_risk_members) AS at_risk_members,
    round(100.0 * sum(h.at_risk_members) / nullif(sum(h.total_members), 0), 2) AS at_risk_percentage,
    sum(h.contactable_members) AS contactable_members
FROM history h
INNER JOIN latest USING (decision_date, run_id)
WHERE (? IS NULL OR h.city_id = ?)
GROUP BY h.decision_date
ORDER BY h.decision_date;
