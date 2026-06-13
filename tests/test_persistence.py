from datetime import datetime, timedelta, timezone

import duckdb

from src.pipeline.marts import build_marts
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
            "metric": "apparent_temperature",
            "operator": "greater_than_or_equal",
            "operator_label": "at or above",
            "threshold": 40.0,
            "persistence_hours": 3,
            "severity": "high",
        }
    ]
    rule_condition = [{"ruleset_version": "test", "rule_id": "three_hour_heat", "condition": "diabetes"}]
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

    raw = tmp_path / "data/raw"
    write_rows(raw / f"source=open_meteo_weather/run_id={run_id}/delhi.parquet", weather)
    write_rows(raw / f"source=open_meteo_air_quality/run_id={run_id}/delhi.parquet", air)
    write_rows(raw / f"source=regional_rules/run_id={run_id}/rule_definitions.parquet", rule_definition)
    write_rows(raw / f"source=regional_rules/run_id={run_id}/rule_conditions.parquet", rule_condition)
    write_rows(raw / f"source=synthetic_members/run_id={run_id}/members.parquet", member)
    write_rows(raw / f"source=synthetic_members/run_id={run_id}/member_conditions.parquet", member_condition)

    build_marts(tmp_path, run_id)

    active_triggers = tmp_path / f"data/processed/run_id={run_id}/active_triggers.parquet"
    assert duckdb.connect().execute(f"SELECT count(*) FROM read_parquet('{active_triggers}')").fetchone()[0] == 0

