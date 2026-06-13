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
    rules = raw / f"source=regional_rules/run_id={run_id}" / "rule_definitions.parquet"
    rule_conditions = raw / f"source=regional_rules/run_id={run_id}" / "rule_conditions.parquet"

    connection.execute(
        f"""
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
          FROM read_parquet('{weather}') w
          INNER JOIN read_parquet('{air}') a USING (city_id, observed_at)
          WHERE w.observed_at >= current_timestamp
        ) TO '{processed / "city_conditions.parquet"}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )
    connection.execute(
        f"""
        COPY (
          WITH metric_values AS (
            SELECT
              city_id,
              observed_at,
              metric,
              metric_value
            FROM read_parquet('{processed / "city_conditions.parquet"}')
            CROSS JOIN LATERAL (
              VALUES
                ('apparent_temperature', apparent_temperature),
                ('precipitation', precipitation),
                ('pm2_5', pm2_5)
            ) metrics(metric, metric_value)
          ),
          evaluated AS (
            SELECT
              r.*,
              m.observed_at,
              m.metric_value,
              lag(m.observed_at) OVER (
                PARTITION BY r.ruleset_version, r.rule_id, r.city_id
                ORDER BY m.observed_at
              ) AS previous_observed_at,
              CASE
                WHEN r.operator = 'greater_than_or_equal' THEN m.metric_value >= r.threshold
                WHEN r.operator = 'less_than_or_equal' THEN m.metric_value <= r.threshold
                ELSE false
              END AS is_breach
            FROM metric_values m
            INNER JOIN read_parquet('{rules}') r
              ON m.city_id = r.city_id
             AND m.metric = r.metric
             AND month(m.observed_at) = r.month
          ),
          grouped AS (
            SELECT
              *,
              sum(
                CASE
                  WHEN NOT is_breach THEN 1
                  WHEN previous_observed_at IS NULL THEN 1
                  WHEN date_diff('hour', previous_observed_at, observed_at) <> 1 THEN 1
                  ELSE 0
                END
              ) OVER (
                PARTITION BY ruleset_version, rule_id, city_id
                ORDER BY observed_at
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
              ) AS streak_group
            FROM evaluated
          ),
          qualifying_streaks AS (
            SELECT
              ruleset_version,
              rule_id,
              city_id,
              metric,
              operator,
              operator_label,
              threshold,
              persistence_hours,
              severity,
              streak_group,
              min(observed_at) AS window_start,
              max(observed_at) AS window_end,
              count(*) AS observed_persistence_hours,
              min(metric_value) AS minimum_metric_value,
              max(metric_value) AS maximum_metric_value
            FROM grouped
            WHERE is_breach
            GROUP BY ALL
            HAVING count(*) >= persistence_hours
          )
          SELECT
            *,
            concat(
              rule_id, ': ', metric, ' remained ', operator_label, ' ', threshold,
              ' for ', observed_persistence_hours, ' consecutive forecast hours in ', city_id, '.'
            ) AS trigger_explanation
          FROM qualifying_streaks
        ) TO '{processed / "active_triggers.parquet"}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )
    connection.execute(
        f"""
        COPY (
          WITH member_base AS (
            SELECT
              m.member_id,
              m.city_id,
              m.age_band,
              m.preferred_language,
              m.preferred_channel,
              m.outreach_consent,
              m.last_contact_date,
              c.condition
            FROM read_parquet('{members}') m
            INNER JOIN read_parquet('{conditions}') c USING (member_id)
            WHERE m.outreach_consent = true
          ),
          eligible AS (
            SELECT
              m.*,
              t.ruleset_version,
              t.rule_id,
              t.metric,
              t.severity,
              t.threshold,
              t.persistence_hours,
              t.observed_persistence_hours,
              t.window_start,
              t.window_end,
              t.minimum_metric_value,
              t.maximum_metric_value,
              t.trigger_explanation,
              CASE t.severity WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END
                + CASE WHEN m.age_band = '60+' THEN 1 ELSE 0 END AS priority_score
            FROM member_base m
            INNER JOIN read_parquet('{processed / "active_triggers.parquet"}') t USING (city_id)
            INNER JOIN read_parquet('{rule_conditions}') rc
              ON t.ruleset_version = rc.ruleset_version
             AND t.rule_id = rc.rule_id
             AND m.condition = rc.condition
          )
          SELECT
            * EXCLUDE (condition),
            list_sort(list_distinct(list(condition))) AS matched_conditions
          FROM eligible
          GROUP BY ALL
        ) TO '{processed / "outreach_queue.parquet"}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )
    connection.execute(
        f"""
        COPY (
          SELECT
            ruleset_version,
            rule_id,
            city_id,
            severity,
            metric,
            threshold,
            persistence_hours,
            observed_persistence_hours,
            window_start,
            window_end,
            trigger_explanation,
            count(DISTINCT member_id) AS eligible_members,
            count(DISTINCT member_id) FILTER (WHERE priority_score >= 4) AS high_priority_members
          FROM read_parquet('{processed / "outreach_queue.parquet"}')
          GROUP BY ALL
        ) TO '{processed / "stakeholder_alerts.parquet"}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )
