COPY (
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
    ),
    previous AS (
        SELECT * FROM read_parquet('{previous_path}')
        WHERE observed_at >= ?
    ),
    changed_incoming AS (
        SELECT incoming.*
        FROM incoming
        LEFT JOIN previous USING (city_id, observed_at)
        WHERE previous.observed_at IS NULL
           OR NOT (
                incoming.pm2_5 IS NOT DISTINCT FROM previous.pm2_5
                AND incoming.pm10 IS NOT DISTINCT FROM previous.pm10
           )
    ),
    retained_previous AS (
        SELECT previous.*
        FROM previous
        LEFT JOIN incoming USING (city_id, observed_at)
        WHERE incoming.observed_at IS NULL
           OR (
                incoming.pm2_5 IS NOT DISTINCT FROM previous.pm2_5
                AND incoming.pm10 IS NOT DISTINCT FROM previous.pm10
           )
    )
    SELECT * FROM changed_incoming
    UNION ALL
    SELECT * FROM retained_previous
    ORDER BY city_id, observed_at
) TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD);
