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
              incoming.pm2_5 IS NOT DISTINCT FROM previous.pm2_5
              AND incoming.pm10 IS NOT DISTINCT FROM previous.pm10
          )
    ) AS updated,
    count(*) FILTER (
        WHERE previous.observed_at IS NOT NULL
          AND incoming.pm2_5 IS NOT DISTINCT FROM previous.pm2_5
          AND incoming.pm10 IS NOT DISTINCT FROM previous.pm10
    ) AS unchanged,
    (SELECT count(*) FROM read_parquet('{incoming_path}')) - count(*) AS rejected
FROM incoming
LEFT JOIN read_parquet('{previous_path}') previous USING (city_id, observed_at);
