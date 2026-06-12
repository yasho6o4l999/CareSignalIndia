from pathlib import Path

import duckdb


def build_marts(root: Path, run_id: str) -> None:
    raw = root / "data/raw"
    processed = root / "data/processed" / f"run_id={run_id}"
    processed.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect()
    weather = raw / f"source=open_meteo_weather/run_id={run_id}" / "*.parquet"
    air = raw / f"source=open_meteo_air_quality/run_id={run_id}" / "*.parquet"
    members = raw / f"source=synthetic_members/run_id={run_id}" / "members.parquet"
    conditions = raw / f"source=synthetic_members/run_id={run_id}" / "member_conditions.parquet"

    connection.execute(
        f"""
        COPY (
          WITH joined AS (
            SELECT
              w.city_id,
              w.observed_at,
              w.apparent_temperature,
              w.precipitation,
              w.relative_humidity,
              w.wind_speed,
              a.pm2_5,
              a.pm10
            FROM read_parquet('{weather}') w
            INNER JOIN read_parquet('{air}') a USING (city_id, observed_at)
            WHERE w.observed_at >= current_timestamp
          )
          SELECT * FROM joined
        ) TO '{processed / "city_conditions.parquet"}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )
    connection.execute(
        f"""
        COPY (
          WITH current_conditions AS (
            SELECT * EXCLUDE (row_number)
            FROM (
              SELECT *, row_number() OVER (PARTITION BY city_id ORDER BY observed_at) AS row_number
              FROM read_parquet('{processed / "city_conditions.parquet"}')
            )
            WHERE row_number = 1
          ),
          member_base AS (
            SELECT
              m.member_id, m.city_id, m.age_band, m.preferred_language, m.preferred_channel,
              m.outreach_consent, m.last_contact_date, c.condition
            FROM read_parquet('{members}') m
            INNER JOIN read_parquet('{conditions}') c USING (member_id)
            WHERE m.outreach_consent = true
          )
          SELECT
            m.*,
            cc.observed_at,
            cc.apparent_temperature,
            cc.precipitation,
            cc.pm2_5,
            CASE
              WHEN cc.pm2_5 >= 60 AND m.condition IN ('respiratory', 'cardiovascular') THEN 'air_quality'
              WHEN cc.apparent_temperature >= 40 THEN 'heat'
              WHEN cc.apparent_temperature <= 10 AND m.condition IN ('respiratory', 'cardiovascular') THEN 'cold'
              WHEN cc.precipitation >= 20 THEN 'heavy_rain'
              ELSE NULL
            END AS trigger_type,
            CASE
              WHEN cc.pm2_5 >= 60 AND m.condition IN ('respiratory', 'cardiovascular') THEN 3
              WHEN cc.apparent_temperature >= 40 THEN 3
              WHEN cc.apparent_temperature <= 10 AND m.condition IN ('respiratory', 'cardiovascular') THEN 2
              WHEN cc.precipitation >= 20 THEN 2
              ELSE 0
            END + CASE WHEN m.age_band = '60+' THEN 1 ELSE 0 END AS priority_score
          FROM member_base m
          INNER JOIN current_conditions cc USING (city_id)
          WHERE trigger_type IS NOT NULL
        ) TO '{processed / "outreach_queue.parquet"}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )
    connection.execute(
        f"""
        COPY (
          SELECT
            city_id,
            trigger_type,
            count(DISTINCT member_id) AS eligible_members,
            count(*) FILTER (WHERE priority_score >= 4) AS high_priority_records,
            max(observed_at) AS condition_time
          FROM read_parquet('{processed / "outreach_queue.parquet"}')
          GROUP BY city_id, trigger_type
        ) TO '{processed / "stakeholder_alerts.parquet"}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )

