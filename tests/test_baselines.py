from datetime import date, datetime, timedelta, timezone

import pyarrow.parquet as pq

from src.pipeline.marts import build_marts
from src.storage import write_rows


def test_baseline_rule_uses_city_month_p95_as_effective_threshold(tmp_path) -> None:
    run_id = "baseline-test"
    start = datetime(2026, 6, 15, 6, tzinfo=timezone.utc)
    weather = [
        {
            "city_id": "bengaluru",
            "observed_at": start + timedelta(hours=offset),
            "apparent_temperature": 37.0,
            "temperature_2m": 36.0,
            "precipitation": 0.0,
            "relative_humidity": 40.0,
            "wind_speed": 5.0,
        }
        for offset in range(3)
    ]
    air = [
        {
            "city_id": "bengaluru",
            "observed_at": start + timedelta(hours=offset),
            "pm2_5": 20.0,
            "pm10": 30.0,
        }
        for offset in range(3)
    ]
    historical = [
        {
            "city_id": "bengaluru",
            "observed_date": datetime(year, 6, day, tzinfo=timezone.utc),
            "temperature_2m": value,
            "minimum_temperature_2m": value - 10,
            "temperature_range": 10.0,
            "precipitation": 0.0,
        }
        for year in range(2021, 2026)
        for day, value in enumerate([30.0, 31.0, 32.0, 33.0, 34.0], start=1)
    ]
    rule_definition = [
        {
            "ruleset_version": "test",
            "rule_id": "local_heat",
            "city_id": "bengaluru",
            "month": 6,
            "condition_logic": "all",
            "predicate_count": 2,
            "persistence_hours": 3,
            "severity": "medium",
            "signal_name": "Local Heat",
            "signal_category": "environmental_health_risk",
        }
    ]
    rule_predicate = [
        {
            "ruleset_version": "test",
            "rule_id": "local_heat",
            "predicate_index": 1,
            "metric": "temperature_2m",
            "operator": "greater_than_or_equal",
            "operator_label": "at or above",
            "comparison": "baseline_percentile",
            "threshold": None,
            "baseline_percentile": "p95",
        },
        {
            "ruleset_version": "test",
            "rule_id": "local_heat",
            "predicate_index": 2,
            "metric": "relative_humidity",
            "operator": "greater_than_or_equal",
            "operator_label": "at or above",
            "comparison": "absolute",
            "threshold": 30.0,
            "baseline_percentile": None,
        },
    ]
    member = [
        {
            "member_id": "M-1",
            "city_id": "bengaluru",
            "age_band": "40-59",
            "preferred_language": "English",
            "preferred_channel": "app",
            "outreach_consent": True,
        },
        {
            "member_id": "M-2",
            "city_id": "bengaluru",
            "age_band": "60+",
            "preferred_language": "English",
            "preferred_channel": "call",
            "outreach_consent": False,
        },
    ]

    raw = tmp_path / "data/raw"
    write_rows(raw / f"source=open_meteo_weather/run_id={run_id}/bengaluru.parquet", weather)
    write_rows(raw / f"source=open_meteo_air_quality/run_id={run_id}/bengaluru.parquet", air)
    write_rows(raw / "source=nasa_power_daily/schema_version=v2/baseline_end_year=2025/city_id=bengaluru/year=2025/data.parquet", historical)
    write_rows(raw / f"source=regional_rules/run_id={run_id}/rule_definitions.parquet", rule_definition)
    write_rows(raw / f"source=regional_rules/run_id={run_id}/rule_predicates.parquet", rule_predicate)
    write_rows(
        raw / f"source=regional_rules/run_id={run_id}/rule_conditions.parquet",
        [{"ruleset_version": "test", "rule_id": "local_heat", "condition": "diabetes", "relevance": "high"}],
    )
    write_rows(
        raw / f"source=regional_rules/run_id={run_id}/rule_severity_bands.parquet",
        [
            {
                "ruleset_version": "test",
                "rule_id": "local_heat",
                "severity": "medium",
                "minimum_persistence_hours": 3,
                "minimum_threshold_ratio": 1.0,
                "severity_rank": 2,
            },
            {
                "ruleset_version": "test",
                "rule_id": "local_heat",
                "severity": "critical",
                "minimum_persistence_hours": 3,
                "minimum_threshold_ratio": 1.0,
                "severity_rank": 4,
            },
        ],
    )
    write_rows(raw / f"source=synthetic_members/run_id={run_id}/members.parquet", member)
    write_rows(
        raw / f"source=synthetic_members/run_id={run_id}/member_conditions.parquet",
        [
            {"member_id": "M-1", "condition": "diabetes"},
            {"member_id": "M-2", "condition": "diabetes"},
        ],
    )

    build_marts(tmp_path, run_id, decision_date=date(2026, 6, 14))

    triggers = pq.read_table(tmp_path / f"data/processed/run_id={run_id}/active_triggers.parquet").to_pylist()
    assert len(triggers) == 1
    assert triggers[0]["predicate_count"] == 2
    assert triggers[0]["metrics"] == ["temperature_2m", "relative_humidity"]
    assert triggers[0]["effective_thresholds"][0] < 36.0
    assert triggers[0]["observed_persistence_hours"] == 3
    assert triggers[0]["severity"] == "critical"
    assert triggers[0]["forecast_start_date"] == date(2026, 6, 15)
    assert triggers[0]["days_until_start"] == 1
    assert triggers[0]["action_timing"] == "upcoming_risk"

    outreach = pq.read_table(tmp_path / f"data/processed/run_id={run_id}/outreach_queue.parquet").to_pylist()
    assert len(outreach) == 1
    assert outreach[0]["action_timing"] == "upcoming_risk"
    assert outreach[0]["days_until_start"] == 1
    risk_exposure = pq.read_table(
        tmp_path / f"data/processed/run_id={run_id}/member_risk_exposure_daily.parquet"
    ).to_pylist()
    assert len(risk_exposure) == 2
    assert {row["outreach_eligible"] for row in risk_exposure} == {True, False}
    workload = pq.read_table(
        tmp_path / f"data/processed/run_id={run_id}/care_workload_daily.parquet"
    ).to_pylist()
    selected_workload = next(row for row in workload if row["decision_date"] == date(2026, 6, 15))
    assert selected_workload["at_risk_members"] == 2
    assert selected_workload["contactable_members"] == 1
    alerts = pq.read_table(
        tmp_path / f"data/processed/run_id={run_id}/stakeholder_alerts.parquet"
    ).to_pylist()
    assert alerts[0]["action_timing"] == "upcoming_risk"
