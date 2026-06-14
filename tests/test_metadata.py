from datetime import date

import pytest

from src.metadata import MetadataStore


def test_metadata_run_lifecycle_and_latest_publication(tmp_path) -> None:
    store = MetadataStore(tmp_path / "pipeline.db")
    store.start_run("run-1", "rules-1", "members-1", 2025, "config-1", "snapshot-1")
    store.record_readiness("run-1", "weather", "delhi", 10, "2026-06-13T00:00:00+00:00")
    store.record_dataset("run-1", "alerts", tmp_path / "alerts.parquet", 3)
    store.upsert_watermark("run-1", "weather", "delhi", "latest_successful_run", "run-1")
    store.complete_run(
        "run-1",
        "success",
        {"extracted": 10, "valid": 10, "invalid": 0, "published": 3},
    )

    latest = store.latest_published_run()
    assert latest["run_id"] == "run-1"
    assert latest["records_published"] == 3
    assert latest["configuration_version"] == "config-1"
    assert latest["member_snapshot_id"] == "snapshot-1"
    assert store.query("queries/latest_source_readiness.sql", ("run-1",))[0]["status"] == "success"
    assert store.watermark("weather", "delhi", "latest_successful_run") == "run-1"
    store.close()


def test_failed_run_does_not_become_latest_published(tmp_path) -> None:
    store = MetadataStore(tmp_path / "pipeline.db")
    counts = {"extracted": 0, "valid": 0, "invalid": 1, "published": 0}
    store.start_run("failed-run", "rules-1", "members-1", 2025)
    store.quarantine("failed-run", "weather", "delhi", ValueError("invalid"), {"bad": "record"})
    store.complete_run("failed-run", "failed", counts, "invalid")

    assert store.latest_published_run() is None
    assert store.query("queries/latest_invalid_counts.sql", ("failed-run",))[0]["invalid_records"] == 1
    store.close()


def test_partial_success_becomes_latest_published_run(tmp_path) -> None:
    store = MetadataStore(tmp_path / "pipeline.db")
    store.start_run("partial-run", "rules-1", "members-1", 2025)
    store.complete_run(
        "partial-run",
        "partial_success",
        {"extracted": 100, "valid": 100, "invalid": 1, "published": 50},
        "one city unavailable",
    )

    latest = store.latest_published_run()
    assert latest["run_id"] == "partial-run"
    assert latest["status"] == "partial_success"
    store.close()


def test_member_dimensions_and_snapshot_registry_are_transactional(tmp_path) -> None:
    store = MetadataStore(tmp_path / "pipeline.db")
    members = [{
        "member_id": "M-1",
        "city_id": "delhi",
        "age_band": "40-59",
        "preferred_language": "Hindi",
        "preferred_channel": "app",
        "outreach_consent": True,
        "last_contact_date": date(2026, 6, 1),
        "generator_version": "v1",
    }]
    conditions = [{"member_id": "M-1", "condition": "diabetes"}]

    metrics = store.reconcile_members(members, conditions, "sync-1")
    store.register_member_snapshot(
        "snapshot-1", "v1", "config-1", tmp_path / "manifest.json", "checksum", 1, 1
    )

    assert store.connection.execute("SELECT count(*) FROM dim_member").fetchone()[0] == 1
    assert store.connection.execute("SELECT count(*) FROM bridge_member_condition").fetchone()[0] == 1
    assert store.connection.execute("SELECT status FROM member_snapshots").fetchone()[0] == "published"
    assert store.current_members()[0]["last_contact_date"] == date(2026, 6, 1)
    assert store.current_member_conditions() == conditions
    assert metrics.inserted == 1
    assert metrics.changed_cities == {"delhi"}
    store.close()


def test_member_reconciliation_tracks_scd2_and_ignores_contact_only_changes(tmp_path) -> None:
    store = MetadataStore(tmp_path / "pipeline.db")
    member = {
        "member_id": "M-1",
        "city_id": "delhi",
        "age_band": "40-59",
        "preferred_language": "Hindi",
        "preferred_channel": "app",
        "outreach_consent": True,
        "last_contact_date": date(2026, 6, 1),
        "generator_version": "v1",
    }
    store.reconcile_members([member], [{"member_id": "M-1", "condition": "diabetes"}], "sync-1")
    contact_only = {**member, "last_contact_date": date(2026, 6, 2)}
    contact_metrics = store.reconcile_members(
        [contact_only], [{"member_id": "M-1", "condition": "diabetes"}], "sync-2"
    )
    moved = {**contact_only, "city_id": "mumbai"}
    moved_metrics = store.reconcile_members(
        [moved], [{"member_id": "M-1", "condition": "respiratory"}], "sync-3"
    )

    assert contact_metrics.unchanged == 1
    assert contact_metrics.changed_cities == {"delhi"}
    assert moved_metrics.updated == 1
    assert moved_metrics.condition_changes == 1
    assert moved_metrics.changed_cities == {"delhi", "mumbai"}
    history = store.connection.execute(
        "SELECT city_id, is_current FROM dim_member_history ORDER BY member_history_sk"
    ).fetchall()
    assert [(row["city_id"], row["is_current"]) for row in history] == [
        ("delhi", 0),
        ("mumbai", 1),
    ]
    assert store.current_members()[0]["last_contact_date"] == date(2026, 6, 2)
    store.close()


def test_member_reconciliation_deactivates_missing_members(tmp_path) -> None:
    store = MetadataStore(tmp_path / "pipeline.db")
    member = {
        "member_id": "M-1",
        "city_id": "delhi",
        "age_band": "40-59",
        "preferred_language": "Hindi",
        "preferred_channel": "app",
        "outreach_consent": True,
        "last_contact_date": date(2026, 6, 1),
        "generator_version": "v1",
    }
    store.reconcile_members([member], [], "sync-1")
    metrics = store.reconcile_members([], [], "sync-2")

    assert metrics.deactivated == 1
    assert metrics.changed_cities == {"delhi"}
    assert store.current_members() == []
    store.close()


def test_member_reconciliation_rejects_orphan_conditions(tmp_path) -> None:
    store = MetadataStore(tmp_path / "pipeline.db")
    with pytest.raises(ValueError, match="unknown members"):
        store.reconcile_members(
            [],
            [{"member_id": "M-unknown", "condition": "diabetes"}],
            "sync-1",
        )
    store.close()
