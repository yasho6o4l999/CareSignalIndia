import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

from src.incremental import ChangeMetrics, merge_forecast_snapshot
from src.reference import file_checksum


def parquet_content_hash(path: Path) -> str:
    table = pq.ParquetFile(path).read()
    volatile_columns = [
        column for column in ("extracted_at", "run_id") if column in table.column_names
    ]
    if volatile_columns:
        table = table.drop(volatile_columns)
    payload = table.sort_by([("city_id", "ascending"), ("observed_at", "ascending")]).to_pylist()
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
        staging.unlink()
        try:
            os.link(previous_path, staging)
        except OSError:
            shutil.copy2(previous_path, staging)
        reused_from = previous_run_id
    table = pq.ParquetFile(staging).read(columns=["observed_at"])
    timestamps = table.column("observed_at").to_pylist()
    manifest = {
        "run_id": run_id,
        "source": source,
        "city_id": city_id,
        "content_hash": content_hash,
        "file_checksum": file_checksum(staging),
        "row_count": len(timestamps),
        "minimum_timestamp": min(timestamps).isoformat(),
        "maximum_timestamp": max(timestamps).isoformat(),
        "reused_from_run_id": reused_from,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    final_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, final_path)
    manifest_path = final_path.with_suffix(".manifest.json")
    temporary_manifest = manifest_path.with_suffix(".json.tmp")
    temporary_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary_manifest, manifest_path)
    return metrics, {**manifest, "file_path": str(final_path), "manifest_path": str(manifest_path)}
