-- Use one newest snapshot per decision date to avoid counting repeated intraday runs twice.
WITH all_history AS (
    SELECT *
    FROM read_parquet('{member_risk_history_path}', hive_partitioning = true)
),
latest_runs AS (
    SELECT decision_date, max(run_id) AS run_id
    FROM all_history
    GROUP BY decision_date
),
history AS (
    SELECT h.*
    FROM all_history h
    INNER JOIN latest_runs USING (decision_date, run_id)
),
selected AS (
    SELECT * FROM history WHERE decision_date = ?
),
previous_date AS (
    SELECT max(decision_date) AS decision_date FROM history WHERE decision_date < ?
),
previous AS (
    SELECT h.* FROM history h INNER JOIN previous_date p USING (decision_date)
),
current_status AS (
    SELECT
        CASE
            WHEN p.member_id IS NULL THEN 'new'
            WHEN s.severity_rank > p.severity_rank THEN 'escalated'
            ELSE 'continuing'
        END AS lifecycle_status,
        s.member_id
    FROM selected s
    LEFT JOIN previous p USING (member_id, city_id, rule_id)
),
resolved AS (
    SELECT 'resolved' AS lifecycle_status, p.member_id
    FROM previous p
    ANTI JOIN selected s USING (member_id, city_id, rule_id)
)
SELECT lifecycle_status, count(DISTINCT member_id) AS members
FROM (
    SELECT * FROM current_status
    UNION ALL
    SELECT * FROM resolved
)
GROUP BY lifecycle_status
ORDER BY lifecycle_status;
