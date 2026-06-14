SELECT
    c.city_id,
    c.signal_name,
    c.severity,
    c.predicate_explanation,
    c.observed_persistence_hours,
    round(t.minimum_value, 1) AS minimum_temperature,
    round(t.maximum_value, 1) AS maximum_temperature
FROM read_parquet('{environmental_conditions_path}') c
LEFT JOIN read_parquet('{environmental_metrics_path}') t
    ON c.decision_date = t.decision_date
   AND c.city_id = t.city_id
   AND t.metric = 'temperature_2m'
WHERE c.decision_date = ?
  AND (? IS NULL OR c.city_id = ?)
ORDER BY c.severity_rank DESC, c.city_id, c.signal_name;
