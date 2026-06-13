SELECT *
FROM read_parquet('{stakeholder_alerts_path}')
ORDER BY eligible_members DESC;

