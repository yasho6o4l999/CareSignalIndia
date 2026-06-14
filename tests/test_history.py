import os
from datetime import datetime, timedelta, timezone

from src.history import HISTORICAL_FACTS, apply_history_retention, publish_history_snapshot


def test_history_snapshot_publishes_daily_facts_atomically(tmp_path) -> None:
    published = tmp_path / "data/processed/run_id=20260614T000000Z"
    published.mkdir(parents=True)
    for name in HISTORICAL_FACTS:
        (published / name).write_text(name, encoding="utf-8")

    snapshot = publish_history_snapshot(tmp_path, "20260614T000000Z", published)

    assert {path.name for path in snapshot.iterdir()} == set(HISTORICAL_FACTS)
    assert not (tmp_path / "data/analytical_history/.staging-20260614T000000Z").exists()
    if os.name != "nt":
        assert (snapshot / HISTORICAL_FACTS[0]).stat().st_ino == (published / HISTORICAL_FACTS[0]).stat().st_ino


def test_history_retention_removes_only_expired_parseable_runs(tmp_path) -> None:
    history = tmp_path / "data/analytical_history"
    expired = history / "run_id=20200101T000000Z"
    current_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    current = history / f"run_id={current_id}"
    unknown = history / "run_id=manual"
    for path in (expired, current, unknown):
        path.mkdir(parents=True)

    apply_history_retention(tmp_path, retention_days=90)

    assert not expired.exists()
    assert current.exists()
    assert unknown.exists()
