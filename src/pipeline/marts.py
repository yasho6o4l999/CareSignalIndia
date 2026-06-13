from datetime import date
from pathlib import Path

import duckdb

from src.sql import render_sql


def build_marts(root: Path, run_id: str) -> None:
    raw = root / "data/raw"
    processed = root / "data/processed" / f"run_id={run_id}"
    processed.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect()

    weather = raw / f"source=open_meteo_weather/run_id={run_id}" / "*.parquet"
    air = raw / f"source=open_meteo_air_quality/run_id={run_id}" / "*.parquet"
    members = raw / f"source=synthetic_members/run_id={run_id}" / "members.parquet"
    member_conditions = raw / f"source=synthetic_members/run_id={run_id}" / "member_conditions.parquet"
    rules = raw / f"source=regional_rules/run_id={run_id}" / "rule_definitions.parquet"
    rule_predicates = raw / f"source=regional_rules/run_id={run_id}" / "rule_predicates.parquet"
    rule_conditions = raw / f"source=regional_rules/run_id={run_id}" / "rule_conditions.parquet"
    history = raw / f"source=nasa_power_daily/schema_version=v2/baseline_end_year={date.today().year - 1}" / "**/*.parquet"
    historical_baselines = processed / "historical_baselines.parquet"
    city_conditions = processed / "city_conditions.parquet"
    active_triggers = processed / "active_triggers.parquet"
    outreach_queue = processed / "outreach_queue.parquet"
    stakeholder_alerts = processed / "stakeholder_alerts.parquet"

    connection.execute(
        render_sql(
            "marts/build_historical_baselines.sql",
            history_path=history,
            output_path=historical_baselines,
        )
    )
    connection.execute(
        render_sql(
            "marts/build_city_conditions.sql",
            weather_path=weather,
            air_path=air,
            output_path=city_conditions,
        )
    )
    connection.execute(
        render_sql(
            "marts/build_active_triggers.sql",
            city_conditions_path=city_conditions,
            rules_path=rules,
            rule_predicates_path=rule_predicates,
            historical_baselines_path=historical_baselines,
            output_path=active_triggers,
        )
    )
    connection.execute(
        render_sql(
            "marts/build_outreach_queue.sql",
            members_path=members,
            member_conditions_path=member_conditions,
            active_triggers_path=active_triggers,
            rule_conditions_path=rule_conditions,
            output_path=outreach_queue,
        )
    )
    connection.execute(
        render_sql(
            "marts/build_stakeholder_alerts.sql",
            outreach_queue_path=outreach_queue,
            output_path=stakeholder_alerts,
        )
    )
