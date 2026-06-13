COPY (
    SELECT
        w.city_id,
        w.observed_at,
        w.apparent_temperature,
        w.precipitation,
        w.relative_humidity,
        w.wind_speed,
        a.pm2_5,
        a.pm10
    FROM read_parquet('{weather_path}') w
    INNER JOIN read_parquet('{air_path}') a USING (city_id, observed_at)
    WHERE w.observed_at >= current_timestamp
) TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD);

