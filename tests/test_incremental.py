from datetime import datetime, timedelta, timezone
import shutil

import pyarrow.parquet as pq
import pytest

from src.config import RawCompactionPolicy
from src.incremental import merge_forecast_snapshot
from src.models import WeatherRecord
from src.raw import (
    cleanup_raw_staging,
    compact_forecast_run,
    publish_forecast_snapshot,
    recover_raw_staging,
    verify_raw_manifest,
)
from src.storage import write_models


def weather_record(observed_at: datetime, temperature: float, extracted_at: datetime) -> WeatherRecord:
    return WeatherRecord(
        city_id="delhi",
        observed_at=observed_at,
        apparent_temperature=temperature + 1,
        temperature_2m=temperature,
        precipitation=0,
        relative_humidity=50,
        wind_speed=5,
        extracted_at=extracted_at,
    )


def test_incremental_merge_classifies_overlap_and_is_idempotent(tmp_path) -> None:
    start = datetime(2099, 1, 1, tzinfo=timezone.utc)
    first_extraction = start - timedelta(hours=1)
    second_extraction = start
    previous_records = [
        weather_record(start + timedelta(hours=offset), 30 + offset, first_extraction)
        for offset in range(3)
    ]
    incoming_records = [
        weather_record(start + timedelta(hours=1), 31, second_extraction),
        weather_record(start + timedelta(hours=2), 40, second_extraction),
        weather_record(start + timedelta(hours=3), 33, second_extraction),
    ]
    previous_path = tmp_path / "previous.parquet"
    output_path = tmp_path / "output.parquet"
    replay_path = tmp_path / "replay.parquet"
    write_models(previous_path, previous_records)

    metrics = merge_forecast_snapshot(
        "open_meteo_weather",
        incoming_records,
        previous_path,
        output_path,
        start - timedelta(hours=1),
    )
    assert (metrics.inserted, metrics.updated, metrics.unchanged) == (1, 1, 1)

    output = sorted(pq.read_table(output_path).to_pylist(), key=lambda row: row["observed_at"])
    assert len(output) == 4
    assert output[1]["extracted_at"] == first_extraction
    assert output[2]["temperature_2m"] == 40

    replay_metrics = merge_forecast_snapshot(
        "open_meteo_weather",
        incoming_records,
        output_path,
        replay_path,
        start - timedelta(hours=1),
    )
    assert (replay_metrics.inserted, replay_metrics.updated, replay_metrics.unchanged) == (0, 0, 3)
    replay = sorted(pq.read_table(replay_path).to_pylist(), key=lambda row: row["observed_at"])
    assert replay == output


def test_initial_snapshot_rejects_duplicate_natural_keys(tmp_path) -> None:
    observed_at = datetime(2099, 1, 1, tzinfo=timezone.utc)
    records = [
        weather_record(observed_at, 30, observed_at - timedelta(hours=1)),
        weather_record(observed_at, 35, observed_at),
    ]
    output_path = tmp_path / "deduplicated.parquet"

    metrics = merge_forecast_snapshot(
        "open_meteo_weather",
        records,
        None,
        output_path,
        observed_at - timedelta(hours=24),
    )

    output = pq.read_table(output_path).to_pylist()
    assert (metrics.inserted, metrics.rejected) == (1, 1)
    assert output[0]["temperature_2m"] == 35


def test_raw_publication_reuses_identical_content_and_writes_manifest(tmp_path) -> None:
    observed_at = datetime(2099, 1, 1, tzinfo=timezone.utc)
    records = [weather_record(observed_at, 30, observed_at)]
    first = tmp_path / "data/raw/source=open_meteo_weather/run_id=run-1/delhi.parquet"
    second = tmp_path / "data/raw/source=open_meteo_weather/run_id=run-2/delhi.parquet"
    _, first_manifest = publish_forecast_snapshot(
        "open_meteo_weather", "delhi", "run-1", records, None, None, first,
        observed_at - timedelta(hours=24),
    )
    replay = [weather_record(observed_at, 30, observed_at + timedelta(hours=1))]
    metrics, second_manifest = publish_forecast_snapshot(
        "open_meteo_weather", "delhi", "run-2", replay, first, "run-1", second,
        observed_at - timedelta(hours=24),
    )

    assert metrics.unchanged == 1
    assert first_manifest["content_hash"] == second_manifest["content_hash"]
    assert second_manifest["reused_from_run_id"] == "run-1"
    assert second_manifest["manifest_version"] == "v2"
    assert second_manifest["schema_version"] == "v1"
    assert second_manifest["schema_fingerprint"]
    assert second_manifest["column_statistics"]
    assert second.with_suffix(".manifest.json").exists()
    assert first.stat().st_ino == second.stat().st_ino


def test_raw_manifest_rejects_incompatible_schema_fingerprint(tmp_path) -> None:
    observed_at = datetime(2099, 1, 1, tzinfo=timezone.utc)
    path = tmp_path / "data/raw/source=open_meteo_weather/run_id=run-1/delhi.parquet"
    _, manifest = publish_forecast_snapshot(
        "open_meteo_weather", "delhi", "run-1",
        [weather_record(observed_at, 30, observed_at)], None, None, path,
        observed_at - timedelta(hours=24),
    )
    incompatible_previous = {**manifest, "schema_fingerprint": "different"}

    with pytest.raises(ValueError, match="Incompatible schema change"):
        verify_raw_manifest(path, manifest, incompatible_previous)


def test_compaction_streams_city_files_into_one_source_artifact(tmp_path) -> None:
    run_id = "run-1"
    observed_at = datetime(2099, 1, 1, tzinfo=timezone.utc)
    run_root = tmp_path / f"source=open_meteo_weather/run_id={run_id}"
    for city_id in ("delhi", "mumbai"):
        records = [
            weather_record(observed_at + timedelta(hours=offset), 30 + offset, observed_at)
            .model_copy(update={"city_id": city_id})
            for offset in range(2)
        ]
        write_models(run_root / f"{city_id}.parquet", records)

    manifest = compact_forecast_run(
        tmp_path,
        "open_meteo_weather",
        run_id,
        RawCompactionPolicy(batch_rows=1000, row_group_rows=1000),
    )
    compacted = run_root / "compacted/data.parquet"

    assert compacted.exists()
    assert manifest["artifact_type"] == "compacted_source_snapshot"
    assert manifest["input_file_count"] == 2
    assert manifest["row_count"] == 4
    assert manifest["row_group_count"] == 1
    assert pq.ParquetFile(compacted).metadata.num_rows == 4

    replay_root = tmp_path / "source=open_meteo_weather/run_id=run-2"
    replay_root.mkdir(parents=True)
    for input_path in run_root.glob("*.parquet"):
        shutil.copy2(input_path, replay_root / input_path.name)
    replay_manifest = compact_forecast_run(
        tmp_path,
        "open_meteo_weather",
        "run-2",
        RawCompactionPolicy(batch_rows=1000, row_group_rows=1000),
    )
    replay_compacted = replay_root / "compacted/data.parquet"

    assert replay_manifest["reused_from_run_id"] == "run-1"
    assert compacted.stat().st_ino == replay_compacted.stat().st_ino


def test_raw_staging_recovery_preserves_active_run(tmp_path) -> None:
    stale = tmp_path / ".staging/source=open_meteo_weather/run_id=stale"
    active = tmp_path / ".staging/source=open_meteo_weather/run_id=active"
    stale.mkdir(parents=True)
    active.mkdir(parents=True)

    removed = recover_raw_staging(tmp_path, "active")

    assert removed == [stale]
    assert not stale.exists()
    assert active.exists()

    cleaned = cleanup_raw_staging(tmp_path, "active")

    assert cleaned == [active]
    assert not (tmp_path / ".staging").exists()
