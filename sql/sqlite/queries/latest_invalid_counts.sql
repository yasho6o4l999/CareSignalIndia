SELECT
    source,
    severity,
    count(DISTINCT coalesce(city_id, '') || ':' || coalesce(natural_key, record_payload))
        AS invalid_records
FROM validation_issue
WHERE run_id = ?
GROUP BY source, severity
ORDER BY source, severity;
