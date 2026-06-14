SELECT city_id, signal_name, severity, predicate_explanation, observed_persistence_hours
FROM read_parquet('{environmental_conditions_path}')
WHERE decision_date = ?
  AND (? IS NULL OR city_id = ?)
ORDER BY severity_rank DESC, city_id, signal_name;
