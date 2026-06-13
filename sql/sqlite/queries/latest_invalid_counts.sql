SELECT source, count(*) AS invalid_records
FROM invalid_records
WHERE run_id = ?
GROUP BY source
ORDER BY source;

