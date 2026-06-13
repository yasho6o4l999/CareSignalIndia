from datetime import datetime, timedelta, timezone

import duckdb

from src.pipeline.marts import build_marts
from src.sql import render_sql
from src.storage import write_rows


def test_missing_hour_breaks_persistence_window(tmp_path) -> None:
    run_id = "test-run"
    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    timestamps = [start, start + timedelta(hours=1), start + timedelta(hours=3), start + timedelta(hours=4)]
    weather = [
        {
            "city_id": "delhi",
            "observed_at": timestamp,
            "apparent_temperature": 41.0,
            "temperature_2m": 40.0,
            "precipitation": 0.0,
            "relative_humidity": 40.0,
            "wind_speed": 5.0,
        }
        for timestamp in timestamps
    ]
    air = [
        {
            "city_id": "delhi",
            "observed_at": timestamp,
            "pm2_5": 20.0,
            "pm10": 30.0,
        }
        for timestamp in timestamps
    ]
    rule_definition = [
        {
            "ruleset_version": "test",
            "rule_id": "three_hour_heat",
            "city_id": "delhi",
            "month": start.month,
            "condition_logic": "all",
            "predicate_count": 1,
            "persistence_hours": 3,
            "severity": "high",
            "signal_name": "Three Hour Heat",
            "signal_category": "environmental_health_risk",
        }
    ]
    rule_predicate = [{
        "ruleset_version": "test",
        "rule_id": "three_hour_heat",
        "predicate_index": 1,
        "metric": "apparent_temperature",
        "operator": "greater_than_or_equal",
        "operator_label": "at or above",
        "comparison": "absolute",
        "threshold": 40.0,
        "baseline_percentile": None,
    }]
    rule_condition = [{
        "ruleset_version": "test",
        "rule_id": "three_hour_heat",
        "condition": "diabetes",
        "relevance": "high",
    }]
    member = [
        {
            "member_id": "M-1",
            "city_id": "delhi",
            "age_band": "40-59",
            "preferred_language": "Hindi",
            "preferred_channel": "app",
            "outreach_consent": True,
            "last_contact_date": start.date(),
        }
    ]
    member_condition = [{"member_id": "M-1", "condition": "diabetes"}]
    historical = [
        {
            "city_id": "delhi",
            "observed_date": start - timedelta(days=365),
            "temperature_2m": 35.0,
            "minimum_temperature_2m": 25.0,
            "temperature_range": 10.0,
            "precipitation": 0.0,
        }
    ]

    raw = tmp_path / "data/raw"
    write_rows(raw / f"source=open_meteo_weather/run_id={run_id}/delhi.parquet", weather)
    write_rows(raw / f"source=open_meteo_air_quality/run_id={run_id}/delhi.parquet", air)
    write_rows(raw / f"source=regional_rules/run_id={run_id}/rule_definitions.parquet", rule_definition)
    write_rows(raw / f"source=regional_rules/run_id={run_id}/rule_predicates.parquet", rule_predicate)
    write_rows(raw / f"source=regional_rules/run_id={run_id}/rule_conditions.parquet", rule_condition)
    write_rows(
        raw / f"source=regional_rules/run_id={run_id}/rule_severity_bands.parquet",
        [{
            "ruleset_version": "test",
            "rule_id": "three_hour_heat",
            "severity": "high",
            "minimum_persistence_hours": 3,
            "minimum_threshold_ratio": 1.0,
            "severity_rank": 3,
        }],
    )
    write_rows(raw / f"source=synthetic_members/run_id={run_id}/members.parquet", member)
    write_rows(raw / f"source=synthetic_members/run_id={run_id}/member_conditions.parquet", member_condition)
    write_rows(raw / "source=nasa_power_daily/schema_version=v2/baseline_end_year=2025/city_id=delhi/year=2025/data.parquet", historical)

    build_marts(tmp_path, run_id)

    active_triggers = tmp_path / f"data/processed/run_id={run_id}/active_triggers.parquet"
    assert duckdb.connect().execute(
        render_sql("common/count_rows.sql", dataset_path=active_triggers)
    ).fetchone()[0] == 0
