WITH publication_cities AS (
    SELECT DISTINCT city_id
    FROM read_parquet('{publication_cities_path}')
),
weather AS (
    SELECT city_id, observed_at
    FROM read_parquet('{weather_path}')
    INNER JOIN publication_cities USING (city_id)
    WHERE observed_at >= current_timestamp
),
air AS (
    SELECT city_id, observed_at
    FROM read_parquet('{air_path}')
    INNER JOIN publication_cities USING (city_id)
    WHERE observed_at >= current_timestamp
),
matched AS (
    SELECT count(*) AS rows
    FROM weather
    INNER JOIN air USING (city_id, observed_at)
),
weather_only AS (
    SELECT count(*) AS rows
    FROM weather
    ANTI JOIN air USING (city_id, observed_at)
),
air_only AS (
    SELECT count(*) AS rows
    FROM air
    ANTI JOIN weather USING (city_id, observed_at)
)
SELECT
    (SELECT count(*) FROM weather) AS weather_rows,
    (SELECT count(*) FROM air) AS air_rows,
    matched.rows AS matched_rows,
    weather_only.rows AS weather_only_rows,
    air_only.rows AS air_only_rows
FROM matched, weather_only, air_only;
