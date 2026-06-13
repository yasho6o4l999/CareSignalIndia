INSERT INTO pipeline_watermarks(
    source, city_id, watermark_type, watermark_value, updated_by_run_id, updated_at
)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(source, city_id, watermark_type) DO UPDATE SET
    watermark_value = excluded.watermark_value,
    updated_by_run_id = excluded.updated_by_run_id,
    updated_at = excluded.updated_at;
