from src.metadata import MetadataStore


def test_metadata_run_lifecycle_and_latest_publication(tmp_path) -> None:
    store = MetadataStore(tmp_path / "pipeline.db")
    store.start_run("run-1", "rules-1", "members-1", 2025)
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
