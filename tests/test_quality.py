from datetime import datetime, timedelta, timezone

import duckdb

from src.config import load_quality_policy
from src.quality import anomaly_result, run_cross_mart_quality_checks, threshold_status
from src.sql import render_sql
from src.storage import write_rows


def test_threshold_status_distinguishes_pass_warning_and_failure() -> None:
    assert threshold_status(0.10, 0.20, 0.40) == "pass"
    assert threshold_status(0.30, 0.20, 0.40) == "warning"
    assert threshold_status(0.50, 0.20, 0.40) == "fail"


def test_historical_anomaly_uses_prior_successful_profile_average() -> None:
    result = anomaly_result(
        "run-2",
        "weather",
        160,
        {("weather", "row_count"): (100.0, 3)},
        load_quality_policy(),
        datetime.now(timezone.utc),
    )

    assert result.status == "fail"
    assert "change_ratio=0.6000" in result.details


def test_cross_source_reconciliation_identifies_each_join_loss_side(tmp_path) -> None:
    now = datetime.now(timezone.utc) + timedelta(hours=1)
    weather_path = tmp_path / "weather.parquet"
    air_path = tmp_path / "air.parquet"
    cities_path = tmp_path / "publication_cities.parquet"
    write_rows(cities_path, [{"city_id": "delhi"}])
    write_rows(weather_path, [
        {"city_id": "delhi", "observed_at": now},
        {"city_id": "delhi", "observed_at": now + timedelta(hours=1)},
        {"city_id": "mumbai", "observed_at": now},
    ])
    write_rows(air_path, [
        {"city_id": "delhi", "observed_at": now},
        {"city_id": "delhi", "observed_at": now + timedelta(hours=2)},
    ])

    connection = duckdb.connect()
    values = connection.execute(render_sql(
        "quality/cross_source_reconciliation.sql",
        weather_path=weather_path,
        air_path=air_path,
        publication_cities_path=cities_path,
    )).fetchone()
    connection.close()

    assert values == (2, 2, 1, 1, 1)


def test_cross_mart_quality_reconciles_published_products(tmp_path) -> None:
    decision_date = datetime(2026, 6, 14, tzinfo=timezone.utc).date()
    trigger = {
        "ruleset_version": "rules-1", "rule_id": "heat", "city_id": "delhi",
        "window_start": datetime(2026, 6, 14, tzinfo=timezone.utc),
        "observed_persistence_hours": 3, "persistence_hours": 3,
    }
    outreach = {
        **trigger, "decision_date": decision_date,
        "member_id": "M-1", "outreach_consent": True, "priority_score": 5,
    }
    alert = {
        "ruleset_version": "rules-1", "rule_id": "heat", "city_id": "delhi",
        "decision_date": decision_date, "window_start": trigger["window_start"],
        "eligible_members": 1, "high_priority_members": 1,
    }
    write_rows(tmp_path / "publication_cities.parquet", [{"city_id": "delhi"}])
    write_rows(tmp_path / "active_triggers.parquet", [trigger])
    write_rows(tmp_path / "outreach_queue.parquet", [outreach])
    write_rows(tmp_path / "stakeholder_alerts.parquet", [alert])
    write_rows(tmp_path / "member_risk_exposure_daily.parquet", [{
        **outreach, "outreach_eligible": True,
    }])
    write_rows(tmp_path / "care_workload_daily.parquet", [{
        "decision_date": decision_date, "city_id": "delhi", "total_members": 1,
        "at_risk_members": 1, "contactable_members": 1, "high_priority_members": 1,
    }])

    checks, profiles = run_cross_mart_quality_checks("run-1", tmp_path)

    assert all(check.status == "pass" for check in checks)
    assert {profile.metric_name for profile in profiles} == {
        "consent_leakage",
        "duplicate_member_triggers",
        "invalid_persistence_windows",
        "orphan_outreach_triggers",
        "stakeholder_reconciliation_errors",
        "unapproved_city_records",
        "outreach_not_in_risk_exposure",
        "workload_reconciliation_errors",
        "at_risk_above_total",
    }


def test_cross_mart_quality_blocks_consent_leakage(tmp_path) -> None:
    window_start = datetime(2026, 6, 14, tzinfo=timezone.utc)
    decision_date = window_start.date()
    trigger = {
        "ruleset_version": "rules-1", "rule_id": "heat", "city_id": "delhi",
        "window_start": window_start, "observed_persistence_hours": 3, "persistence_hours": 3,
    }
    write_rows(tmp_path / "publication_cities.parquet", [{"city_id": "delhi"}])
    write_rows(tmp_path / "active_triggers.parquet", [trigger])
    write_rows(tmp_path / "outreach_queue.parquet", [{
        **trigger, "decision_date": decision_date,
        "member_id": "M-1", "outreach_consent": False, "priority_score": 5,
    }])
    write_rows(tmp_path / "stakeholder_alerts.parquet", [{
        "ruleset_version": "rules-1", "rule_id": "heat", "city_id": "delhi",
        "decision_date": decision_date, "window_start": window_start,
        "eligible_members": 1, "high_priority_members": 1,
    }])
    write_rows(tmp_path / "member_risk_exposure_daily.parquet", [{
        **trigger, "decision_date": decision_date, "member_id": "M-1",
        "outreach_consent": False, "outreach_eligible": False, "priority_score": 5,
    }])
    write_rows(tmp_path / "care_workload_daily.parquet", [{
        "decision_date": decision_date, "city_id": "delhi", "total_members": 1,
        "at_risk_members": 1, "contactable_members": 0, "high_priority_members": 1,
    }])

    checks, _ = run_cross_mart_quality_checks("run-1", tmp_path)

    consent_check = next(check for check in checks if check.check_name == "consent_leakage")
    assert consent_check.status == "fail"
    assert consent_check.details == "actual=1, maximum=0"
