SELECT *
FROM read_parquet('{stakeholder_alerts_path}')
WHERE action_timing = ?
ORDER BY days_until_start, severity DESC, eligible_members DESC;
