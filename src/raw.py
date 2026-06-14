import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from src.config import RawCompactionPolicy
from src.incremental import ChangeMetrics, merge_forecast_snapshot
from src.reference import file_checksum


RAW_MANIFEST_VERSION = "v2"
RAW_SCHEMA_VERSION = "v1"


def parquet_content_hash(path: Path) -> str:
    """Hash business content while ignoring run-specific extraction metadata."""
    digest = hashlib.sha256()
    parquet = pq.ParquetFile(path)
    columns = [
        column for column in parquet.schema_arrow.names if column not in {"extracted_at", "run_id"}
    ]
    for batch in parquet.iter_batches(batch_size=65536, columns=columns):
        for row in batch.to_pylist():
            canonical = json.dumps(row, sort_keys=True, default=str, separators=(",", ":"))
            digest.update(canonical.encode("utf-8"))
            digest.update(b"\n")
    return digest.hexdigest()


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def schema_fingerprint(path: Path) -> tuple[str, list[dict]]:
    fields = [
        {"name": field.name, "type": str(field.type), "nullable": field.nullable}
        for field in pq.read_schema(path)
    ]
    canonical = json.dumps(fields, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), fields


def parquet_column_statistics(path: Path) -> list[dict]:
    parquet = pq.ParquetFile(path)
    schema = parquet.schema_arrow
    statistics = []
    for index, field in enumerate(schema):
        null_count = 0
        minimum = maximum = None
        for row_group_index in range(parquet.metadata.num_row_groups):
            column = parquet.metadata.row_group(row_group_index).column(index)
            stats = column.statistics
            if stats is None:
                continue
            null_count += stats.null_count or 0
            if stats.has_min_max:
                candidate_min = _json_value(stats.min)
                candidate_max = _json_value(stats.max)
                minimum = candidate_min if minimum is None or candidate_min < minimum else minimum
                maximum = candidate_max if maximum is None or candidate_max > maximum else maximum
        statistics.append(
            {
                "name": field.name,
                "type": str(field.type),
                "null_count": null_count,
                "minimum": minimum,
                "maximum": maximum,
            }
        )
    return statistics


def build_raw_manifest(
    path: Path,
    source: str,
    city_id: str,
    run_id: str,
    reused_from_run_id: str | None = None,
    artifact_type: str = "city_snapshot",
    input_file_count: int = 1,
) -> dict:
    parquet = pq.ParquetFile(path)
    fingerprint, schema = schema_fingerprint(path)
    column_statistics = parquet_column_statistics(path)
    timestamp_statistics = next(
        item for item in column_statistics if item["name"] == "observed_at"
    )
    return {
        "manifest_version": RAW_MANIFEST_VERSION,
        "schema_version": RAW_SCHEMA_VERSION,
        "schema_fingerprint": fingerprint,
        "schema": schema,
        "artifact_type": artifact_type,
        "run_id": run_id,
        "source": source,
        "city_id": city_id,
        "content_hash": parquet_content_hash(path),
        "file_checksum": file_checksum(path),
        "file_size_bytes": path.stat().st_size,
        "row_count": parquet.metadata.num_rows,
        "row_group_count": parquet.metadata.num_row_groups,
        "input_file_count": input_file_count,
        "minimum_timestamp": timestamp_statistics["minimum"],
        "maximum_timestamp": timestamp_statistics["maximum"],
        "column_statistics": column_statistics,
        "reused_from_run_id": reused_from_run_id,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }


def verify_raw_manifest(path: Path, manifest: dict, previous_manifest: dict | None = None) -> None:
    if manifest.get("manifest_version") != RAW_MANIFEST_VERSION:
        raise ValueError(f"Unsupported raw manifest version for {path}")
    if manifest.get("schema_version") != RAW_SCHEMA_VERSION:
        raise ValueError(f"Unsupported raw schema version for {path}")
    fingerprint, _ = schema_fingerprint(path)
    if fingerprint != manifest["schema_fingerprint"]:
        raise ValueError(f"Schema fingerprint mismatch for {path}")
    if file_checksum(path) != manifest["file_checksum"]:
        raise ValueError(f"Checksum mismatch for {path}")
    if pq.ParquetFile(path).metadata.num_rows != manifest["row_count"]:
        raise ValueError(f"Row-count mismatch for {path}")
    if previous_manifest and previous_manifest.get("schema_version") == manifest["schema_version"]:
        previous_fingerprint = previous_manifest.get("schema_fingerprint")
        if previous_fingerprint and previous_fingerprint != fingerprint:
            raise ValueError(
                f"Incompatible schema change for {path}; increment raw schema_version before publishing"
            )


def recover_raw_staging(raw_root: Path, active_run_id: str) -> list[Path]:
    removed = []
    staging_root = raw_root / ".staging"
    if not staging_root.exists():
        return removed
    for path in staging_root.glob("source=*/run_id=*"):
        if path.name == f"run_id={active_run_id}":
            continue
        shutil.rmtree(path)
        removed.append(path)
    return removed


def cleanup_raw_staging(raw_root: Path, run_id: str) -> list[Path]:
    removed = []
    staging_root = raw_root / ".staging"
    for source_root in staging_root.glob("source=*"):
        run_root = source_root / f"run_id={run_id}"
        if run_root.exists():
            shutil.rmtree(run_root)
            removed.append(run_root)
        if source_root.exists() and not any(source_root.iterdir()):
            source_root.rmdir()
    if staging_root.exists() and not any(staging_root.iterdir()):
        staging_root.rmdir()
    return removed


def compact_forecast_run(
    raw_root: Path,
    source: str,
    run_id: str,
    policy: RawCompactionPolicy,
) -> dict | None:
    """Stream city snapshots into a governed source-level file with bounded memory."""
    if not policy.enabled:
        return None
    run_root = raw_root / f"source={source}" / f"run_id={run_id}"
    inputs = sorted(run_root.glob("*.parquet"))
    if not inputs:
        return None
    final_path = run_root / "compacted/data.parquet"
    staging_path = raw_root / ".staging" / f"source={source}" / f"run_id={run_id}/compacted.parquet"
    staging_path.parent.mkdir(parents=True, exist_ok=True)
    writer = None
    buffered_batches = []
    buffered_rows = 0
    try:
        for input_path in inputs:
            parquet = pq.ParquetFile(input_path)
            writer = writer or pq.ParquetWriter(
                staging_path, parquet.schema_arrow, compression=policy.compression
            )
            for batch in parquet.iter_batches(batch_size=policy.batch_rows):
                buffered_batches.append(batch)
                buffered_rows += batch.num_rows
                if buffered_rows >= policy.row_group_rows:
                    writer.write_table(
                        pa.Table.from_batches(buffered_batches),
                        row_group_size=policy.row_group_rows,
                    )
                    buffered_batches.clear()
                    buffered_rows = 0
        if buffered_batches:
            writer.write_table(
                pa.Table.from_batches(buffered_batches),
                row_group_size=policy.row_group_rows,
            )
        writer.close()
        writer = None
        manifest = build_raw_manifest(
            staging_path, source, "__all__", run_id,
            artifact_type="compacted_source_snapshot", input_file_count=len(inputs),
        )
        previous_manifest_paths = sorted(
            (
                path
                for path in (raw_root / f"source={source}").glob(
                    "run_id=*/compacted/data.manifest.json"
                )
                if f"run_id={run_id}" not in str(path)
            ),
            reverse=True,
        )
        previous_manifest = (
            json.loads(previous_manifest_paths[0].read_text(encoding="utf-8"))
            if previous_manifest_paths
            else None
        )
        verify_raw_manifest(staging_path, manifest, previous_manifest)
        if previous_manifest and previous_manifest["content_hash"] == manifest["content_hash"]:
            # Preserve an immutable run view while reusing identical compacted bytes.
            previous_path = previous_manifest_paths[0].parent / "data.parquet"
            staging_path.unlink()
            try:
                os.link(previous_path, staging_path)
            except OSError:
                shutil.copy2(previous_path, staging_path)
            manifest = build_raw_manifest(
                staging_path, source, "__all__", run_id,
                reused_from_run_id=previous_manifest["run_id"],
                artifact_type="compacted_source_snapshot", input_file_count=len(inputs),
            )
            verify_raw_manifest(staging_path, manifest, previous_manifest)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging_path, final_path)
        manifest_path = final_path.with_suffix(".manifest.json")
        temporary_manifest = manifest_path.with_suffix(".json.tmp")
        temporary_manifest.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary_manifest, manifest_path)
        return {**manifest, "file_path": str(final_path), "manifest_path": str(manifest_path)}
    finally:
        if writer:
            writer.close()
        if staging_path.exists():
            staging_path.unlink()


def publish_forecast_snapshot(
    source: str,
    city_id: str,
    run_id: str,
    incoming_records: list,
    previous_path: Path | None,
    previous_run_id: str | None,
    final_path: Path,
    cutoff: datetime,
) -> tuple[ChangeMetrics, dict]:
    """Validate and atomically publish one incremental source-city snapshot."""
    staging = (
        final_path.parents[2]
        / ".staging"
        / f"source={source}"
        / f"run_id={run_id}"
        / final_path.name
    )
    staging.parent.mkdir(parents=True, exist_ok=True)
    metrics = merge_forecast_snapshot(source, incoming_records, previous_path, staging, cutoff)
    content_hash = parquet_content_hash(staging)
    reused_from = None
    if previous_path and previous_path.exists() and parquet_content_hash(previous_path) == content_hash:
        # A hard link avoids duplicate storage; the new manifest still records reuse lineage.
        staging.unlink()
        try:
            os.link(previous_path, staging)
        except OSError:
            shutil.copy2(previous_path, staging)
        reused_from = previous_run_id
    manifest = build_raw_manifest(staging, source, city_id, run_id, reused_from)
    previous_manifest_path = previous_path.with_suffix(".manifest.json") if previous_path else None
    previous_manifest = (
        json.loads(previous_manifest_path.read_text(encoding="utf-8"))
        if previous_manifest_path and previous_manifest_path.exists()
        else None
    )
    verify_raw_manifest(staging, manifest, previous_manifest)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, final_path)
    manifest_path = final_path.with_suffix(".manifest.json")
    temporary_manifest = manifest_path.with_suffix(".json.tmp")
    temporary_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary_manifest, manifest_path)
    return metrics, {**manifest, "file_path": str(final_path), "manifest_path": str(manifest_path)}
