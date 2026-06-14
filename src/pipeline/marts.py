from datetime import date
from pathlib import Path

import duckdb

from src.sql import render_sql


def build_marts(
    root: Path,
    run_id: str,
    processed: Path | None = None,
    members_root: Path | None = None,
    rules_root: Path | None = None,
    publication_cities: Path | None = None,
    decision_date: date | None = None,
    decision_timezone: str = "Asia/Kolkata",
) -> None:
    """Build analytical products in dependency order into a private staging directory."""
    raw = root / "data/raw"
    processed = processed or root / "data/processed" / f"run_id={run_id}"
    processed.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect()

    weather_root = raw / f"source=open_meteo_weather/run_id={run_id}"
    air_root = raw / f"source=open_meteo_air_quality/run_id={run_id}"
    weather = (
        weather_root / "compacted/data.parquet"
        if (weather_root / "compacted/data.parquet").exists()
        else weather_root / "*.parquet"
    )
    air = (
        air_root / "compacted/data.parquet"
        if (air_root / "compacted/data.parquet").exists()
        else air_root / "*.parquet"
    )
    members_root = members_root or raw / f"source=synthetic_members/run_id={run_id}"
    rules_root = rules_root or raw / f"source=regional_rules/run_id={run_id}"
    partitioned_members = members_root / "members"
    partitioned_conditions = members_root / "member_conditions"
    members = (
        partitioned_members / "**/*.parquet"
        if partitioned_members.exists()
        else members_root / "members.parquet"
    )
    publication_cities = publication_cities or members
    member_conditions = (
        partitioned_conditions / "**/*.parquet"
        if partitioned_conditions.exists()
        else members_root / "member_conditions.parquet"
    )
    rules = rules_root / "rule_definitions.parquet"
    rule_predicates = rules_root / "rule_predicates.parquet"
    rule_conditions = rules_root / "rule_conditions.parquet"
    rule_severity_bands = rules_root / "rule_severity_bands.parquet"
    history = raw / f"source=nasa_power_daily/schema_version=v2/baseline_end_year={date.today().year - 1}" / "**/*.parquet"
    historical_baselines = processed / "historical_baselines.parquet"
    city_conditions = processed / "city_conditions.parquet"
    active_triggers = processed / "active_triggers.parquet"
    environmental_conditions_daily = processed / "environmental_conditions_daily.parquet"
    environmental_metrics_daily = processed / "environmental_metrics_daily.parquet"
    member_risk_exposure_daily = processed / "member_risk_exposure_daily.parquet"
    care_workload_daily = processed / "care_workload_daily.parquet"
    outreach_queue = processed / "outreach_queue.parquet"
    stakeholder_alerts = processed / "stakeholder_alerts.parquet"
    decision_date = decision_date or date.today()

    # Downstream facts are deliberately sequenced after their validated upstream artifacts.
    connection.execute(
        render_sql(
            "marts/build_historical_baselines.sql",
            history_path=history,
            publication_cities_path=publication_cities,
            output_path=historical_baselines,
        )
    )
    connection.execute(
        render_sql(
            "marts/build_city_conditions.sql",
            weather_path=weather,
            air_path=air,
            publication_cities_path=publication_cities,
            output_path=city_conditions,
        )
    )
    connection.execute(
        render_sql(
            "marts/build_active_triggers.sql",
            city_conditions_path=city_conditions,
            rules_path=rules,
            rule_predicates_path=rule_predicates,
            rule_severity_bands_path=rule_severity_bands,
            historical_baselines_path=historical_baselines,
            decision_date=decision_date.isoformat(),
            decision_timezone=decision_timezone,
            output_path=active_triggers,
        )
    )
    connection.execute(
        render_sql(
            "marts/build_environmental_conditions_daily.sql",
            active_triggers_path=active_triggers,
            decision_timezone=decision_timezone,
            output_path=environmental_conditions_daily,
        )
    )
    connection.execute(
        render_sql(
            "marts/build_environmental_metrics_daily.sql",
            city_conditions_path=city_conditions,
            historical_baselines_path=historical_baselines,
            decision_timezone=decision_timezone,
            output_path=environmental_metrics_daily,
        )
    )
    connection.execute(
        render_sql(
            "marts/build_member_risk_exposure_daily.sql",
            members_path=members,
            member_conditions_path=member_conditions,
            environmental_conditions_daily_path=environmental_conditions_daily,
            rule_conditions_path=rule_conditions,
            output_path=member_risk_exposure_daily,
        )
    )
    connection.execute(
        render_sql(
            "marts/build_care_workload_daily.sql",
            members_path=members,
            publication_cities_path=publication_cities,
            environmental_metrics_daily_path=environmental_metrics_daily,
            member_risk_exposure_daily_path=member_risk_exposure_daily,
            output_path=care_workload_daily,
        )
    )
    connection.execute(
        render_sql(
            "marts/build_outreach_queue.sql",
            member_risk_exposure_daily_path=member_risk_exposure_daily,
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
    connection.close()
