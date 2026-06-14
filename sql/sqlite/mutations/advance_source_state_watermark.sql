UPDATE source_pipeline_state
SET watermark_type = ?,
    previous_watermark_value = (
        SELECT resulting_watermark_value
        FROM current_source_state
        WHERE source = ? AND city_id = ? AND watermark_type = ?
    ),
    resulting_watermark_value = ?,
    watermark_advanced = 1
WHERE run_id = ? AND source = ? AND city_id = ? AND status = 'success';
