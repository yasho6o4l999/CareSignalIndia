SELECT resulting_watermark_value AS watermark_value
FROM source_pipeline_state
WHERE source = ?
  AND city_id = ?
  AND watermark_type = ?
  AND status = 'success'
  AND watermark_advanced = 1
ORDER BY extraction_completed_at DESC, run_id DESC
LIMIT 1;
