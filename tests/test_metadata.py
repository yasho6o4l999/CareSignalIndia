from datetime import date, datetime, timezone

import pytest

from src.metadata import MetadataStore
from src.models import QualityResult
from src.quality import QualityProfile


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


def test_records_extraction_metrics_and_raw_manifest(tmp_path) -> None:
    store = MetadataStore(tmp_path / "pipeline.db")
    store.start_run("run-1", "rules-1", "members-1", 2025)
    store.record_extraction_metrics("run-1", [{
        "source": "open_meteo_weather",
        "city_id": "delhi",
        "duration_ms": 100,
        "attempts": 2,
        "http_status": 200,
        "response_bytes": 500,
        "status": "success",
    }])
    store.record_raw_manifest({
        "run_id": "run-1",
        "source": "open_meteo_weather",
        "city_id": "delhi",
        "file_path": "/tmp/data.parquet",
        "manifest_path": "/tmp/data.manifest.json",
        "content_hash": "content",
        "file_checksum": "file",
        "row_count": 10,
        "minimum_timestamp": "2026-01-01T00:00:00+00:00",
        "maximum_timestamp": "2026-01-01T09:00:00+00:00",
        "reused_from_run_id": None,
        "published_at": "2026-01-01T10:00:00+00:00",
    })

    assert store.connection.execute("SELECT attempts FROM extraction_metrics").fetchone()[0] == 2
    assert store.latest_raw_manifest("open_meteo_weather", "delhi")["content_hash"] == "content"
    store.close()


def test_structured_quarantine_persists_field_level_evidence(tmp_path) -> None:
    store = MetadataStore(tmp_path / "pipeline.db")
    store.start_run("run-1", "rules-1", "members-1", 2025)
    store.quarantine(
        "run-1", "open_meteo_weather", "delhi", ValueError("invalid humidity"),
        {"observed_at": "2026-01-01", "relative_humidity": 101},
        field_name="relative_humidity", natural_key="2026-01-01", invalid_value=101,
    )

    row = store.connection.execute("SELECT * FROM invalid_records").fetchone()
    assert row["field_name"] == "relative_humidity"
    assert row["natural_key"] == "2026-01-01"
    assert row["invalid_value"] == "101"
    assert row["severity"] == "fatal"
    store.close()


def test_quarantine_issues_preserves_original_error_type(tmp_path) -> None:
    from src.validation import ValidationIssue

    store = MetadataStore(tmp_path / "pipeline.db")
    store.start_run("run-1", "rules-1", "members-1", 2025)
    store.quarantine_issues("run-1", "open_meteo_air_quality", "delhi", [
        ValidationIssue(
            natural_key="2026-01-01", field_name="pm2_5",
            error_type="cross_field_pm25_above_pm10", invalid_value=50,
            error_message="PM2.5 exceeds PM10", record_payload={"pm2_5": 50, "pm10": 40},
            severity="warning",
        )
    ])
    row = store.connection.execute("SELECT error_type, severity FROM invalid_records").fetchone()
    assert tuple(row) == ("cross_field_pm25_above_pm10", "warning")
    store.close()


def test_invalid_summary_counts_records_instead_of_field_issues(tmp_path) -> None:
    from src.validation import ValidationIssue

    store = MetadataStore(tmp_path / "pipeline.db")
    store.start_run("run-1", "rules-1", "members-1", 2025)
    store.quarantine_issues("run-1", "open_meteo_air_quality", "delhi", [
        ValidationIssue(
            natural_key="2026-01-01", field_name=field_name, error_type="missing_value",
            invalid_value=None, error_message="missing", record_payload={field_name: None},
        )
        for field_name in ("pm2_5", "pm10")
    ])

    summary = store.query("queries/latest_invalid_counts.sql", ("run-1",))
    assert summary[0]["invalid_records"] == 1
    store.close()


def test_operational_control_plane_unifies_source_state_and_atomic_finalization(tmp_path) -> None:
    store = MetadataStore(tmp_path / "pipeline.db")
    store.start_run("run-1", "rules-1", "members-1", 2025)
    store.record_extraction_metrics("run-1", [{
        "source": "weather", "city_id": "delhi", "duration_ms": 100, "attempts": 2,
        "http_status": 200, "response_bytes": 500, "status": "success",
    }])
    store.record_readiness(
        "run-1", "weather", "delhi", 10, "2026-06-13T00:00:00+00:00",
        inserted=2, unchanged=8,
    )
    store.finalize_run(
        "run-1", "success",
        {"extracted": 10, "valid": 10, "invalid": 0, "published": 3},
        [("weather", "delhi", "latest_successful_run", "run-1")],
    )

    source = store.connection.execute(
        "SELECT * FROM source_pipeline_state WHERE run_id = 'run-1'"
    ).fetchone()
    assert source["attempts"] == 2
    assert source["records_inserted"] == 2
    assert source["resulting_watermark_value"] == "run-1"
    assert source["watermark_advanced"] == 1
    assert store.watermark("weather", "delhi", "latest_successful_run") == "run-1"
    assert store.connection.execute(
        "SELECT status FROM operational_run WHERE run_id = 'run-1'"
    ).fetchone()[0] == "success"
    store.close()


def test_artifact_registry_tracks_reuse_and_compaction_lineage(tmp_path) -> None:
    store = MetadataStore(tmp_path / "pipeline.db")
    for run_id in ("run-1", "run-2"):
        store.start_run(run_id, "rules-1", "members-1", 2025)
    base = {
        "source": "open_meteo_weather", "file_path": "/tmp/data.parquet",
        "manifest_path": "/tmp/data.manifest.json", "content_hash": "content",
        "file_checksum": "file", "row_count": 10,
        "minimum_timestamp": "2026-01-01T00:00:00+00:00",
        "maximum_timestamp": "2026-01-01T09:00:00+00:00",
        "published_at": "2026-01-01T10:00:00+00:00",
    }
    store.record_raw_manifest({**base, "run_id": "run-1", "city_id": "delhi", "reused_from_run_id": None})
    store.record_raw_manifest({
        **base, "run_id": "run-2", "city_id": "delhi", "reused_from_run_id": "run-1",
    })
    store.record_raw_manifest({
        **base, "run_id": "run-2", "city_id": "__all__", "reused_from_run_id": None,
        "artifact_type": "compacted_source_snapshot",
    })

    relationships = {
        row[0]
        for row in store.connection.execute("SELECT relationship_type FROM artifact_dependency")
    }
    assert relationships == {"reused_from", "compacted_from"}
    store.close()


def test_quality_results_and_reference_metadata_are_normalized(tmp_path) -> None:
    store = MetadataStore(tmp_path / "pipeline.db")
    store.start_run("run-1", "rules-1", "members-1", 2025)
    store.record_quality_results([
        QualityResult(
            run_id="run-1", check_name="non_empty", dataset="weather", status="pass",
            details="rows=10", checked_at=datetime.now(timezone.utc),
        )
    ])
    store.record_quality_profiles([
        QualityProfile(
            run_id="run-1", stage="source", dataset="weather", metric_name="row_count",
            metric_value=100, recorded_at=datetime.now(timezone.utc),
        )
    ])
    store.register_member_snapshot(
        "snapshot-1", "v1", "config-1", tmp_path / "manifest.json", "checksum", 1, 2
    )

    assert store.connection.execute("SELECT count(*) FROM quality_check_result").fetchone()[0] == 1
    store.complete_run(
        "run-1", "success",
        {"extracted": 100, "valid": 100, "invalid": 0, "published": 1},
    )
    store.start_run("run-2", "rules-1", "members-1", 2025)
    assert store.previous_quality_profiles("run-2")[("weather", "row_count")] == (100.0, 1)
    reference = store.connection.execute("SELECT * FROM reference_snapshot").fetchone()
    assert reference["snapshot_type"] == "member"
    assert reference["primary_record_count"] == 1
    assert reference["related_record_count"] == 2
    store.maintain()
    store.close()


def test_pipeline_stage_execution_records_success_and_failure(tmp_path) -> None:
    store = MetadataStore(tmp_path / "pipeline.db")
    store.start_run("run-1", "rules-1", "members-1", 2025)
    store.start_stage("run-1", "extract_forecasts", 10)
    store.complete_stage("run-1", "extract_forecasts", "success", 125, 20)
    store.start_stage("run-1", "build_marts", 20)
    store.complete_stage("run-1", "build_marts", "failed", 50, 0, "broken")

    rows = store.query("queries/latest_pipeline_stages.sql", ("run-1",))
    assert [(row["stage_name"], row["status"]) for row in rows] == [
        ("extract_forecasts", "success"),
        ("build_marts", "failed"),
    ]
    assert rows[0]["input_records"] == 10
    assert rows[0]["output_records"] == 20
    store.close()
