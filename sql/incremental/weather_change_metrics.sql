WITH incoming AS (
    SELECT * EXCLUDE (natural_key_rank)
    FROM (
        SELECT
            *,
            row_number() OVER (
                PARTITION BY city_id, observed_at
                ORDER BY extracted_at DESC
            ) AS natural_key_rank
        FROM read_parquet('{incoming_path}')
    )
    WHERE natural_key_rank = 1
)
SELECT
    count(*) FILTER (WHERE previous.observed_at IS NULL) AS inserted,
    count(*) FILTER (
        WHERE previous.observed_at IS NOT NULL
          AND NOT (
              incoming.apparent_temperature IS NOT DISTINCT FROM previous.apparent_temperature
              AND incoming.temperature_2m IS NOT DISTINCT FROM previous.temperature_2m
              AND incoming.precipitation IS NOT DISTINCT FROM previous.precipitation
              AND incoming.relative_humidity IS NOT DISTINCT FROM previous.relative_humidity
              AND incoming.wind_speed IS NOT DISTINCT FROM previous.wind_speed
          )
    ) AS updated,
    count(*) FILTER (
        WHERE previous.observed_at IS NOT NULL
          AND incoming.apparent_temperature IS NOT DISTINCT FROM previous.apparent_temperature
          AND incoming.temperature_2m IS NOT DISTINCT FROM previous.temperature_2m
          AND incoming.precipitation IS NOT DISTINCT FROM previous.precipitation
          AND incoming.relative_humidity IS NOT DISTINCT FROM previous.relative_humidity
          AND incoming.wind_speed IS NOT DISTINCT FROM previous.wind_speed
    ) AS unchanged,
    (SELECT count(*) FROM read_parquet('{incoming_path}')) - count(*) AS rejected
FROM incoming
LEFT JOIN read_parquet('{previous_path}') previous USING (city_id, observed_at);
