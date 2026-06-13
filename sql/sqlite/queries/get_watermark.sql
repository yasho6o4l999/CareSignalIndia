SELECT watermark_value
FROM pipeline_watermarks
WHERE source = ?
  AND city_id = ?
  AND watermark_type = ?;
