COPY (
    WITH joined AS (
        SELECT
        w.city_id,
        w.observed_at,
        w.apparent_temperature,
        w.temperature_2m,
        w.precipitation,
        w.relative_humidity,
        w.wind_speed,
        a.pm2_5,
        a.pm10
        FROM read_parquet('{weather_path}') w
        INNER JOIN read_parquet('{air_path}') a USING (city_id, observed_at)
        INNER JOIN (
            SELECT DISTINCT city_id
            FROM read_parquet('{publication_cities_path}')
        ) publication_cities USING (city_id)
        WHERE w.observed_at >= current_timestamp
    )
    SELECT
        *,
        apparent_temperature - temperature_2m AS apparent_temperature_uplift,
        sum(precipitation) OVER (
            PARTITION BY city_id, CAST(observed_at AS DATE)
        ) AS daily_precipitation_sum,
        min(temperature_2m) OVER (
            PARTITION BY city_id, CAST(observed_at AS DATE)
        ) AS daily_min_temperature,
        max(temperature_2m) OVER (
            PARTITION BY city_id, CAST(observed_at AS DATE)
        ) AS daily_max_temperature,
        max(temperature_2m) OVER (
            PARTITION BY city_id, CAST(observed_at AS DATE)
        ) - min(temperature_2m) OVER (
            PARTITION BY city_id, CAST(observed_at AS DATE)
        ) AS daily_temperature_range
    FROM joined
) TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD);
