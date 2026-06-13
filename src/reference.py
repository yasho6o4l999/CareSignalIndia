import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

from src.storage import write_rows


MANIFEST_NAME = "manifest.json"
MEMBER_SCHEMA_VERSION = "v2"


def file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_checksum(manifest: dict) -> str:
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_member_rows(members: list[dict], conditions: list[dict]) -> None:
    member_ids = [member["member_id"] for member in members]
    if not members or len(member_ids) != len(set(member_ids)):
        raise ValueError("Member snapshot must contain unique, non-empty member IDs")
    unknown = {row["member_id"] for row in conditions} - set(member_ids)
    if unknown:
        raise ValueError(f"Member conditions reference unknown members: {sorted(unknown)[:5]}")
    condition_keys = [(row["member_id"], row["condition"]) for row in conditions]
    if len(condition_keys) != len(set(condition_keys)):
        raise ValueError("Member snapshot contains duplicate member-condition links")


def _write_member_partitions(staging: Path, members: list[dict], conditions: list[dict]) -> None:
    member_city = {member["member_id"]: member["city_id"] for member in members}
    by_city: dict[str, list[dict]] = {}
    conditions_by_city: dict[str, list[dict]] = {}
    for member in members:
        by_city.setdefault(member["city_id"], []).append(member)
    for condition in conditions:
        conditions_by_city.setdefault(member_city[condition["member_id"]], []).append(condition)
    for city_id, rows in by_city.items():
        write_rows(staging / f"members/city_id={city_id}/data.parquet", rows)
        write_rows(
            staging / f"member_conditions/city_id={city_id}/data.parquet",
            conditions_by_city.get(city_id, []),
        )


def _build_manifest(
    staging: Path,
    snapshot_id: str,
    configuration_version: str,
    members: list[dict],
    conditions: list[dict],
) -> dict:
    files = []
    for path in sorted(staging.rglob("*.parquet")):
        files.append(
            {
                "path": str(path.relative_to(staging)),
                "rows": pq.ParquetFile(path).metadata.num_rows,
                "size_bytes": path.stat().st_size,
                "sha256": file_checksum(path),
                "schema": str(pq.read_schema(path)),
            }
        )
    return {
        "snapshot_id": snapshot_id,
        "schema_version": MEMBER_SCHEMA_VERSION,
        "configuration_version": configuration_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "member_count": len(members),
        "condition_count": len(conditions),
        "files": files,
    }


def verify_member_snapshot(root: Path) -> dict:
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.exists():
        raise ValueError(f"Missing member snapshot manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest["files"]:
        path = root / item["path"]
        if not path.exists():
            raise ValueError(f"Missing member snapshot file: {path}")
        if file_checksum(path) != item["sha256"]:
            raise ValueError(f"Checksum mismatch for member snapshot file: {path}")
        if pq.ParquetFile(path).metadata.num_rows != item["rows"]:
            raise ValueError(f"Row-count mismatch for member snapshot file: {path}")
        if str(pq.read_schema(path)) != item["schema"]:
            raise ValueError(f"Schema mismatch for member snapshot file: {path}")
    member_rows = sum(item["rows"] for item in manifest["files"] if item["path"].startswith("members/"))
    condition_rows = sum(
        item["rows"] for item in manifest["files"] if item["path"].startswith("member_conditions/")
    )
    if member_rows != manifest["member_count"] or condition_rows != manifest["condition_count"]:
        raise ValueError("Member snapshot manifest totals do not match its files")
    return manifest


def publish_member_snapshot(
    reference_root: Path,
    snapshot_id: str,
    configuration_version: str,
    members: list[dict],
    conditions: list[dict],
) -> tuple[Path, dict, str]:
    _validate_member_rows(members, conditions)
    final = reference_root / f"snapshot_id={snapshot_id}"
    if final.exists():
        manifest = verify_member_snapshot(final)
        return final, manifest, manifest_checksum(manifest)
    staging = reference_root / f".staging-{snapshot_id}"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        _write_member_partitions(staging, members, conditions)
        manifest = _build_manifest(staging, snapshot_id, configuration_version, members, conditions)
        (staging / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        verify_member_snapshot(staging)
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, final)
        return final, manifest, manifest_checksum(manifest)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
