import re
from pathlib import Path

from src.config import ROOT
from src.sql import render_sql


EXPECTED_SQL_FILES = {
    "benchmark/member_scale_dashboard.sql",
    "common/count_rows.sql",
    "dashboard/outreach_member_count.sql",
    "dashboard/outreach_queue.sql",
    "dashboard/historical_baselines.sql",
    "dashboard/available_dates.sql",
    "dashboard/city_comparison.sql",
    "dashboard/condition_workload.sql",
    "dashboard/contact_channel_workload.sql",
    "dashboard/contact_mode_summary.sql",
    "dashboard/environmental_metrics_daily.sql",
    "dashboard/environmental_ticker.sql",
    "dashboard/executive_kpis.sql",
    "dashboard/member_risk_exposure.sql",
    "dashboard/outreach_readiness_by_city.sql",
    "dashboard/quality_issue_count.sql",
    "dashboard/risk_trend.sql",
    "dashboard/risk_driver_impact.sql",
    "dashboard/risk_lifecycle_summary.sql",
    "dashboard/severity_summary.sql",
    "dashboard/stakeholder_alerts.sql",
    "incremental/air_quality_change_metrics.sql",
    "incremental/deduplicate_forecast_snapshot.sql",
    "incremental/merge_air_quality_snapshot.sql",
    "incremental/merge_weather_snapshot.sql",
    "incremental/weather_change_metrics.sql",
    "marts/build_active_triggers.sql",
    "marts/build_city_conditions.sql",
    "marts/build_care_workload_daily.sql",
    "marts/build_environmental_conditions_daily.sql",
    "marts/build_environmental_metrics_daily.sql",
    "marts/build_historical_baselines.sql",
    "marts/build_outreach_queue.sql",
    "marts/build_member_risk_exposure_daily.sql",
    "marts/build_stakeholder_alerts.sql",
    "quality/profile_dataset.sql",
    "quality/profile_historical_dataset.sql",
    "quality/publication_contract.sql",
    "quality/cross_source_reconciliation.sql",
    "quality/cross_mart_integrity.sql",
}


def test_expected_sql_artifacts_are_versioned() -> None:
    actual = {
        str(path.relative_to(ROOT / "sql"))
        for path in (ROOT / "sql").rglob("*.sql")
    }
    assert EXPECTED_SQL_FILES <= actual


def test_production_python_does_not_embed_sql() -> None:
    production_files = [ROOT / "app.py", *(ROOT / "src").rglob("*.py")]
    sql_pattern = re.compile(r"\b(SELECT|COPY|read_parquet)\b", re.IGNORECASE)

    for path in production_files:
        assert not sql_pattern.search(path.read_text(encoding="utf-8")), f"Embedded SQL found in {path}"


def test_sql_renderer_escapes_path_quotes() -> None:
    rendered = render_sql("common/count_rows.sql", dataset_path=Path("/tmp/member's.parquet"))
    assert "/tmp/member''s.parquet" in rendered
