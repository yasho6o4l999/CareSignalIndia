COPY (
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
    ORDER BY city_id, observed_at
) TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD);
