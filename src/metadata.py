import json
import sqlite3
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import cache
from pathlib import Path
from typing import Any

from src.config import ROOT
from src.models import QualityResult
from src.quality import QualityProfile
from src.validation import ValidationIssue


DATABASE_PATH = ROOT / "data/metadata/pipeline.db"
SQLITE_ROOT = ROOT / "sql/sqlite"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_sql(relative_path: str) -> str:
    return (SQLITE_ROOT / relative_path).read_text(encoding="utf-8")


@cache
def read_named_statement(directory: str, statement_name: str) -> str:
    """Resolve one named statement from a consolidated SQLite bundle."""
    matches = []
    pattern = re.compile(
        rf"^-- name: {re.escape(statement_name)}\s*$\n(.*?)(?=^-- name: |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    for path in (SQLITE_ROOT / directory).glob("*_statements.sql"):
        if match := pattern.search(path.read_text(encoding="utf-8")):
            matches.append(match.group(1).strip())
    if len(matches) != 1:
        raise ValueError(f"Expected one mutation named {statement_name!r}, found {len(matches)}")
    return matches[0]


def read_mutation(statement_name: str) -> str:
    return read_named_statement("mutations", statement_name)


def read_query(statement_name: str) -> str:
    return read_named_statement("queries", statement_name)


@dataclass(frozen=True)
class MemberSyncMetrics:
    inserted: int
    updated: int
    deactivated: int
    unchanged: int
    condition_changes: int
    changed_cities: frozenset[str]


class RunRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def start(
        self,
        run_id: str,
        started_at: str,
        ruleset_version: str,
        member_version: str,
        baseline_end_year: int,
        configuration_version: str | None,
        member_snapshot_id: str | None,
    ) -> None:
        values = (
            run_id, started_at, ruleset_version, member_version, baseline_end_year,
            configuration_version, member_snapshot_id,
        )
        self.connection.execute(read_mutation("start_operational_run"), values)
        self.connection.execute(read_mutation("start_operational_run_metric"), (run_id,))

    def complete(
        self,
        run_id: str,
        status: str,
        counts: dict[str, int],
        completed_at: str,
        error_message: str | None,
    ) -> None:
        self.connection.execute(
            read_mutation("complete_operational_run"),
            (completed_at, status, completed_at, status, error_message, run_id),
        )
        self.connection.execute(
            read_mutation("complete_operational_run_metric"),
            (
                counts["extracted"], counts["valid"], counts["invalid"], counts["published"],
                counts.get("inserted", 0), counts.get("updated", 0),
                counts.get("unchanged", 0), counts.get("rejected", counts["invalid"]), run_id,
            ),
        )


class SourceStateRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def record_success(
        self,
        run_id: str,
        source: str,
        city_id: str,
        now: str,
        records: int,
        latest: str | None,
        inserted: int,
        updated: int,
        unchanged: int,
        rejected: int,
    ) -> None:
        self.connection.execute(
            read_mutation("upsert_source_state_success"),
            (
                run_id, source, city_id, now, now, records, records - rejected, rejected,
                inserted, updated, unchanged, rejected, latest, run_id, source, city_id,
            ),
        )

    def record_failure(self, run_id: str, source: str, city_id: str, now: str, message: str) -> None:
        self.connection.execute(
            read_mutation("upsert_source_state_failure"),
            (run_id, source, city_id, now, message, run_id, source, city_id),
        )

    def advance_watermark(
        self, run_id: str, source: str, city_id: str, watermark_type: str, value: str
    ) -> None:
        self.connection.execute(
            read_mutation("advance_source_state_watermark"),
            (watermark_type, source, city_id, watermark_type, value, run_id, source, city_id),
        )

    def watermark(self, source: str, city_id: str, watermark_type: str) -> str | None:
        row = self.connection.execute(
            read_query("current_source_watermark"), (source, city_id, watermark_type)
        ).fetchone()
        return row["watermark_value"] if row else None


class ArtifactRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    @staticmethod
    def raw_id(run_id: str, source: str, city_id: str) -> str:
        return f"raw:{run_id}:{source}:{city_id}"

    def record_raw(self, manifest: dict) -> None:
        artifact_id = self.raw_id(manifest["run_id"], manifest["source"], manifest["city_id"])
        self.connection.execute(
            read_mutation("record_data_artifact"),
            (
                artifact_id, manifest["run_id"], manifest.get("artifact_type", "city_snapshot"),
                manifest["source"], manifest["source"], manifest["city_id"],
                manifest["file_path"], manifest["manifest_path"], manifest["content_hash"],
                manifest["file_checksum"], manifest.get("schema_version"),
                manifest.get("schema_fingerprint"), manifest["row_count"],
                manifest.get("file_size_bytes"), manifest.get("row_group_count"),
                manifest.get("input_file_count"), manifest["minimum_timestamp"],
                manifest["maximum_timestamp"], manifest["published_at"],
            ),
        )
        reused_from = manifest.get("reused_from_run_id")
        if reused_from:
            self.connection.execute(
                read_mutation("record_artifact_dependency"),
                (
                    self.raw_id(reused_from, manifest["source"], manifest["city_id"]),
                    artifact_id, "reused_from", manifest["published_at"],
                ),
            )
        if manifest.get("artifact_type") == "compacted_source_snapshot":
            parents = self.connection.execute(
                read_query("source_run_city_artifacts"),
                (manifest["run_id"], manifest["source"]),
            ).fetchall()
            self.connection.executemany(
                read_mutation("record_artifact_dependency"),
                [
                    (row["artifact_id"], artifact_id, "compacted_from", manifest["published_at"])
                    for row in parents
                ],
            )

    def record_processed(self, run_id: str, name: str, path: Path, count: int, published_at: str) -> None:
        artifact_id = f"processed:{run_id}:{name}"
        self.connection.execute(
            read_mutation("record_data_artifact"),
            (
                artifact_id, run_id, "processed_dataset", name, None, None,
                str(path), None, None, None, None, None, count,
                path.stat().st_size if path.exists() else None,
                None, None, None, None, published_at,
            ),
        )
        upstream = self.connection.execute(
            read_query("run_upstream_artifacts"), (run_id, run_id)
        ).fetchall()
        self.connection.executemany(
            read_mutation("record_artifact_dependency"),
            [
                (row["artifact_id"], artifact_id, "derived_from", published_at)
                for row in upstream
            ],
        )

    def record_reference(
        self,
        snapshot_id: str,
        manifest_path: Path,
        checksum: str,
        count: int,
        published_at: str,
    ) -> None:
        self.connection.execute(
            read_mutation("record_data_artifact"),
            (
                f"reference:member:{snapshot_id}", None, "reference_snapshot", snapshot_id,
                None, None, str(manifest_path), str(manifest_path), None, checksum, None, None,
                count, manifest_path.stat().st_size if manifest_path.exists() else None,
                None, None, None, None, published_at,
            ),
        )


class QualityRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def record_results(self, results: list[QualityResult]) -> None:
        self.connection.executemany(
            read_mutation("record_quality_result"),
            [
                (
                    result.run_id, result.check_name, result.dataset, result.status,
                    result.details, result.checked_at.isoformat(),
                )
                for result in results
            ],
        )

    def record_profiles(self, profiles: list[QualityProfile]) -> None:
        self.connection.executemany(
            read_mutation("record_quality_profile"),
            [
                (
                    profile.run_id, profile.stage, profile.dataset, profile.metric_name,
                    profile.metric_value, profile.recorded_at.isoformat(),
                )
                for profile in profiles
            ],
        )

    def previous_profiles(
        self, run_id: str, stage: str = "source"
    ) -> dict[tuple[str, str], tuple[float, int]]:
        return {
            (row["dataset"], row["metric_name"]): (row["average_value"], row["sample_count"])
            for row in self.connection.execute(
                read_query("previous_quality_profiles"), (stage, run_id)
            ).fetchall()
        }


class MemberRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def record_snapshot(
        self,
        snapshot_id: str,
        generator_version: str,
        configuration_version: str,
        manifest_path: Path,
        checksum: str,
        member_count: int,
        condition_count: int,
        created_at: str,
    ) -> None:
        self.connection.execute(
            read_mutation("register_reference_snapshot"),
            (
                snapshot_id, generator_version, configuration_version, str(manifest_path),
                checksum, member_count, condition_count, created_at,
            ),
        )

    def protected_snapshot_ids(self) -> set[str]:
        return {
            row["member_snapshot_id"]
            for row in self.connection.execute(
                read_query("protected_member_snapshots")
            ).fetchall()
        }

    def latest_snapshot_id(self) -> str | None:
        row = self.connection.execute(read_query("latest_member_snapshot")).fetchone()
        return row["snapshot_id"] if row else None

    def delete_snapshot_records(self, snapshot_ids: list[str]) -> None:
        self.connection.executemany(
            read_mutation("delete_reference_snapshot"),
            [(snapshot_id,) for snapshot_id in snapshot_ids],
        )


class MetadataStore:
    def __init__(self, path: Path = DATABASE_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(read_sql("session_pragmas.sql"))
        self._apply_migrations()
        self.runs = RunRepository(self.connection)
        self.sources = SourceStateRepository(self.connection)
        self.artifacts = ArtifactRepository(self.connection)
        self.quality = QualityRepository(self.connection)
        self.members = MemberRepository(self.connection)

    def _apply_migrations(self) -> None:
        # Ordered, recorded migrations make both fresh installs and upgrades deterministic.
        self.connection.executescript(read_sql("migrations/000_schema_migrations.sql"))
        applied = {
            row["version"]
            for row in self.connection.execute(read_query("applied_migrations")).fetchall()
        }
        if "000_schema_migrations.sql" not in applied:
            with self.connection:
                self.connection.execute(
                    read_mutation("record_migration"),
                    ("000_schema_migrations.sql", utc_now()),
                )
            applied.add("000_schema_migrations.sql")
        for path in sorted((SQLITE_ROOT / "migrations").glob("*.sql")):
            if path.name in applied:
                continue
            with self.connection:
                self.connection.executescript(path.read_text(encoding="utf-8"))
                self.connection.execute(
                    read_mutation("record_migration"),
                    (path.name, utc_now()),
                )

    def close(self) -> None:
        self.connection.close()

    def maintain(self) -> None:
        self.connection.executescript(read_sql("maintenance.sql"))

    def start_run(
        self,
        run_id: str,
        ruleset_version: str,
        member_version: str,
        baseline_end_year: int,
        configuration_version: str | None = None,
        member_snapshot_id: str | None = None,
    ) -> None:
        started_at = utc_now()
        with self.connection:
            self.runs.start(
                run_id, started_at, ruleset_version, member_version, baseline_end_year,
                configuration_version, member_snapshot_id,
            )

    @staticmethod
    def _member_hash(row: dict) -> str:
        payload = {
            key: row[key]
            for key in (
                "member_id", "city_id", "age_band", "preferred_language",
                "preferred_channel", "outreach_consent", "generator_version",
            )
        }
        canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def reconcile_members(
        self,
        members: list[dict],
        conditions: list[dict],
        sync_id: str,
    ) -> MemberSyncMetrics:
        started_at = utc_now()
        member_ids = [row["member_id"] for row in members]
        if len(member_ids) != len(set(member_ids)):
            raise ValueError("Member source contains duplicate member IDs")
        unknown_condition_members = {row["member_id"] for row in conditions} - set(member_ids)
        if unknown_condition_members:
            raise ValueError(
                f"Member conditions reference unknown members: {sorted(unknown_condition_members)[:5]}"
            )
        existing = {
            row["member_id"]: dict(row)
            for row in self.connection.execute(read_query("member_state")).fetchall()
        }
        existing_conditions: dict[str, set[str]] = {}
        for row in self.connection.execute(
            read_query("all_member_conditions")
        ).fetchall():
            existing_conditions.setdefault(row["member_id"], set()).add(row["condition"])
        incoming = {row["member_id"]: row for row in members}
        incoming_conditions: dict[str, set[str]] = {}
        for row in conditions:
            incoming_conditions.setdefault(row["member_id"], set()).add(row["condition"])
        inserted = updated = deactivated = unchanged = condition_changes = 0
        changed_cities: set[str] = set()
        now = utc_now()

        with self.connection:
            for member_id, row in incoming.items():
                source_hash = self._member_hash(row)
                previous = existing.get(member_id)
                changed = previous is None or previous["source_hash"] != source_hash or not previous["is_active"]
                if previous is None:
                    inserted += 1
                elif changed:
                    updated += 1
                    changed_cities.add(previous["city_id"])
                else:
                    unchanged += 1
                if changed:
                    changed_cities.add(row["city_id"])
                    self.connection.execute(
                        read_mutation("upsert_member"),
                        (
                            member_id, row["city_id"], row["age_band"], row["preferred_language"],
                            row["preferred_channel"], int(row["outreach_consent"]),
                            row["generator_version"], now, source_hash,
                        ),
                    )
                if existing_conditions.get(member_id, set()) != incoming_conditions.get(member_id, set()):
                    condition_changes += 1
                    changed_cities.add(row["city_id"])
                    self.connection.execute(
                        read_mutation("delete_member_conditions"), (member_id,)
                    )
                    self.connection.executemany(
                        read_mutation("insert_member_condition"),
                        [
                            (member_id, condition)
                            for condition in sorted(incoming_conditions.get(member_id, set()))
                        ],
                    )
            for member_id in existing.keys() - incoming.keys():
                previous = existing[member_id]
                if previous["is_active"]:
                    deactivated += 1
                    changed_cities.add(previous["city_id"])
                    self.connection.execute(
                        read_mutation("deactivate_member"), (now, member_id)
                    )
                    self.connection.execute(
                        read_mutation("delete_member_conditions"), (member_id,)
                    )
            self.connection.execute(
                read_mutation("record_reference_sync"),
                (
                    sync_id, started_at, utc_now(), inserted, updated, deactivated, unchanged,
                    condition_changes, json.dumps(sorted(changed_cities)),
                ),
            )
        return MemberSyncMetrics(
            inserted=inserted,
            updated=updated,
            deactivated=deactivated,
            unchanged=unchanged,
            condition_changes=condition_changes,
            changed_cities=frozenset(changed_cities),
        )

    def register_member_snapshot(
        self,
        snapshot_id: str,
        generator_version: str,
        configuration_version: str,
        manifest_path: Path,
        checksum: str,
        member_count: int,
        condition_count: int,
    ) -> None:
        created_at = utc_now()
        with self.connection:
            self.members.record_snapshot(
                snapshot_id, generator_version, configuration_version, manifest_path,
                checksum, member_count, condition_count, created_at,
            )
            self.artifacts.record_reference(
                snapshot_id, manifest_path, checksum, member_count, created_at
            )

    def current_members(self) -> list[dict]:
        return [
            {
                **dict(row),
                "outreach_consent": bool(row["outreach_consent"]),
            }
            for row in self.connection.execute(read_query("current_members")).fetchall()
        ]

    def current_member_conditions(self) -> list[dict]:
        return [
            dict(row)
            for row in self.connection.execute(
                read_query("current_member_conditions")
            ).fetchall()
        ]

    def protected_member_snapshot_ids(self) -> set[str]:
        return self.members.protected_snapshot_ids()

    def latest_member_snapshot_id(self) -> str | None:
        return self.members.latest_snapshot_id()

    def delete_member_snapshot_records(self, snapshot_ids: list[str]) -> None:
        with self.connection:
            self.members.delete_snapshot_records(snapshot_ids)

    def complete_run(self, run_id: str, status: str, counts: dict[str, int], error_message: str | None = None) -> None:
        now = utc_now()
        with self.connection:
            self.runs.complete(run_id, status, counts, now, error_message)

    def record_readiness(
        self,
        run_id: str,
        source: str,
        city_id: str,
        records: int,
        latest: str | None,
        inserted: int = 0,
        updated: int = 0,
        unchanged: int = 0,
        rejected: int = 0,
    ) -> None:
        now = utc_now()
        with self.connection:
            self.sources.record_success(
                run_id, source, city_id, now, records, latest, inserted, updated, unchanged, rejected
            )

    def record_extraction_request_metrics(self, run_id: str, metrics: list[dict]) -> None:
        with self.connection:
            self.connection.executemany(
                read_mutation("record_extraction_request_metric"),
                [
                    (
                        run_id, metric["source"], metric["city_id"], metric["duration_ms"],
                        metric["attempts"], metric["http_status"], metric["response_bytes"],
                        metric["status"], utc_now(),
                    )
                    for metric in metrics
                ],
            )

    def start_stage(self, run_id: str, stage_name: str, input_records: int = 0) -> None:
        with self.connection:
            self.connection.execute(
                read_mutation("start_pipeline_stage"),
                (run_id, stage_name, utc_now(), input_records),
            )

    def complete_stage(
        self,
        run_id: str,
        stage_name: str,
        status: str,
        duration_ms: int,
        output_records: int = 0,
        error_message: str | None = None,
    ) -> None:
        with self.connection:
            self.connection.execute(
                read_mutation("complete_pipeline_stage"),
                (utc_now(), status, duration_ms, output_records, error_message, run_id, stage_name),
            )

    def record_raw_manifest(self, manifest: dict) -> None:
        with self.connection:
            self.artifacts.record_raw(manifest)

    def latest_raw_manifest(self, source: str, city_id: str) -> sqlite3.Row | None:
        return self.connection.execute(
            read_query("latest_raw_manifest"), (source, city_id)
        ).fetchone()

    def record_failure(self, run_id: str, source: str, city_id: str, message: str) -> None:
        now = utc_now()
        with self.connection:
            self.sources.record_failure(run_id, source, city_id, now, message)

    def quarantine(
        self,
        run_id: str,
        source: str,
        city_id: str | None,
        error: Exception,
        payload: Any,
        field_name: str | None = None,
        natural_key: str | None = None,
        invalid_value: Any = None,
        severity: str = "fatal",
    ) -> None:
        quarantined_at = utc_now()
        record_payload = json.dumps(payload, default=str)
        invalid_json = json.dumps(invalid_value, default=str)
        with self.connection:
            self.connection.execute(
                read_mutation("record_validation_issue"),
                (
                    run_id, source, city_id, severity, natural_key, field_name, type(error).__name__,
                    invalid_json, str(error), record_payload, "v1", quarantined_at,
                ),
            )

    def quarantine_issues(
        self,
        run_id: str,
        source: str,
        city_id: str,
        issues: list[ValidationIssue],
    ) -> None:
        quarantined_at = utc_now()
        with self.connection:
            self.connection.executemany(
                read_mutation("record_validation_issue"),
                [
                    (
                        run_id, source, city_id, issue.severity, issue.natural_key,
                        issue.field_name, issue.error_type, json.dumps(issue.invalid_value, default=str),
                        issue.error_message, json.dumps(issue.record_payload, default=str),
                        "v1", quarantined_at,
                    )
                    for issue in issues
                ],
            )

    def record_dataset(self, run_id: str, name: str, path: Path, count: int) -> None:
        published_at = utc_now()
        with self.connection:
            self.artifacts.record_processed(run_id, name, path, count, published_at)

    def upsert_watermark(self, run_id: str, source: str, city_id: str, watermark_type: str, value: str) -> None:
        with self.connection:
            self.sources.advance_watermark(run_id, source, city_id, watermark_type, value)

    def watermark(self, source: str, city_id: str, watermark_type: str) -> str | None:
        return self.sources.watermark(source, city_id, watermark_type)

    def record_quality_results(self, results: list[QualityResult]) -> None:
        with self.connection:
            self.quality.record_results(results)

    def record_quality_profiles(self, profiles: list[QualityProfile]) -> None:
        with self.connection:
            self.quality.record_profiles(profiles)

    def previous_quality_profiles(
        self, run_id: str, stage: str = "source"
    ) -> dict[tuple[str, str], tuple[float, int]]:
        return self.quality.previous_profiles(run_id, stage)

    def finalize_run(
        self,
        run_id: str,
        status: str,
        counts: dict[str, int],
        watermarks: list[tuple[str, str, str, str]],
        error_message: str | None = None,
    ) -> None:
        now = utc_now()
        # Publication status and successful watermarks advance atomically.
        with self.connection:
            for source, city_id, watermark_type, value in watermarks:
                self.sources.advance_watermark(run_id, source, city_id, watermark_type, value)
            self.runs.complete(run_id, status, counts, now, error_message)

    def latest_published_run(self) -> sqlite3.Row | None:
        return self.connection.execute(read_query("latest_published_run")).fetchone()

    def query(self, statement_name: str, parameters: tuple = ()) -> list[sqlite3.Row]:
        return self.connection.execute(read_query(statement_name), parameters).fetchall()
