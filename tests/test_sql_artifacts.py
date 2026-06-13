import re
from pathlib import Path

from src.config import ROOT
from src.sql import render_sql


EXPECTED_SQL_FILES = {
    "common/count_rows.sql",
    "dashboard/outreach_member_count.sql",
    "dashboard/outreach_queue.sql",
    "dashboard/historical_baselines.sql",
    "dashboard/quality_issue_count.sql",
    "dashboard/stakeholder_alerts.sql",
    "marts/build_active_triggers.sql",
    "marts/build_city_conditions.sql",
    "marts/build_historical_baselines.sql",
    "marts/build_outreach_queue.sql",
    "marts/build_stakeholder_alerts.sql",
    "quality/profile_dataset.sql",
    "quality/profile_historical_dataset.sql",
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
