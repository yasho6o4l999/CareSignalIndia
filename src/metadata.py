import json
import sqlite3
import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from src.config import ROOT
from src.validation import ValidationIssue


DATABASE_PATH = ROOT / "data/metadata/pipeline.db"
SQLITE_ROOT = ROOT / "sql/sqlite"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_sql(relative_path: str) -> str:
    return (SQLITE_ROOT / relative_path).read_text(encoding="utf-8")


@dataclass(frozen=True)
class MemberSyncMetrics:
    inserted: int
    updated: int
    deactivated: int
    unchanged: int
    condition_changes: int
    changed_cities: frozenset[str]


class MetadataStore:
    def __init__(self, path: Path = DATABASE_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(read_sql("session_pragmas.sql"))
        self._apply_migrations()

    def _apply_migrations(self) -> None:
        self.connection.executescript(read_sql("migrations/000_schema_migrations.sql"))
        applied = {
            row["version"]
            for row in self.connection.execute(read_sql("queries/applied_migrations.sql")).fetchall()
        }
        if "000_schema_migrations.sql" not in applied:
            with self.connection:
                self.connection.execute(
                    read_sql("mutations/record_migration.sql"),
                    ("000_schema_migrations.sql", utc_now()),
                )
            applied.add("000_schema_migrations.sql")
        for path in sorted((SQLITE_ROOT / "migrations").glob("*.sql")):
            if path.name in applied:
                continue
            with self.connection:
                self.connection.executescript(path.read_text(encoding="utf-8"))
                self.connection.execute(
                    read_sql("mutations/record_migration.sql"),
                    (path.name, utc_now()),
                )

    def close(self) -> None:
        self.connection.close()

    def start_run(
        self,
        run_id: str,
        ruleset_version: str,
        member_version: str,
        baseline_end_year: int,
        configuration_version: str | None = None,
        member_snapshot_id: str | None = None,
    ) -> None:
        with self.connection:
            self.connection.execute(
                read_sql("mutations/start_run.sql"),
                (
                    run_id, utc_now(), ruleset_version, member_version, baseline_end_year,
                    configuration_version, member_snapshot_id,
                ),
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
        activity_source: str = "synthetic_generator",
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
            for row in self.connection.execute(read_sql("queries/member_state.sql")).fetchall()
        }
        existing_conditions: dict[str, set[str]] = {}
        for row in self.connection.execute(
            read_sql("queries/all_member_conditions.sql")
        ).fetchall():
            existing_conditions.setdefault(row["member_id"], set()).add(row["condition"])
        incoming = {row["member_id"]: row for row in members}
        incoming_conditions: dict[str, set[str]] = {}
        for row in conditions:
            incoming_conditions.setdefault(row["member_id"], set()).add(row["condition"])
        existing_contacts = {
            row["member_id"]: row["last_contact_date"] for row in self.current_members()
        }
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
                    self.connection.execute(
                        read_sql("mutations/close_member_history.sql"), (now, member_id)
                    )
                else:
                    unchanged += 1
                if changed:
                    changed_cities.add(row["city_id"])
                    self.connection.execute(
                        read_sql("mutations/upsert_member.sql"),
                        (
                            member_id, row["city_id"], row["age_band"], row["preferred_language"],
                            row["preferred_channel"], int(row["outreach_consent"]),
                            row["last_contact_date"].isoformat(), row["generator_version"], now,
                            source_hash,
                        ),
                    )
                    self.connection.execute(
                        read_sql("mutations/insert_member_history.sql"),
                        (
                            member_id, row["city_id"], row["age_band"], row["preferred_language"],
                            row["preferred_channel"], int(row["outreach_consent"]),
                            row["generator_version"], source_hash, now,
                        ),
                    )
                self.connection.execute(
                    read_sql("mutations/record_outreach_activity.sql"),
                    (member_id, row["last_contact_date"].isoformat(), activity_source),
                )
                if existing_contacts.get(member_id) != row["last_contact_date"]:
                    changed_cities.add(row["city_id"])
                if existing_conditions.get(member_id, set()) != incoming_conditions.get(member_id, set()):
                    condition_changes += 1
                    changed_cities.add(row["city_id"])
                    self.connection.execute(
                        read_sql("mutations/delete_member_conditions.sql"), (member_id,)
                    )
                    self.connection.executemany(
                        read_sql("mutations/insert_member_condition.sql"),
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
                        read_sql("mutations/deactivate_member.sql"), (now, member_id)
                    )
                    self.connection.execute(
                        read_sql("mutations/close_member_history.sql"), (now, member_id)
                    )
                    self.connection.execute(
                        read_sql("mutations/delete_member_conditions.sql"), (member_id,)
                    )
            self.connection.execute(
                read_sql("mutations/record_member_sync.sql"),
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
        with self.connection:
            self.connection.execute(
                read_sql("mutations/register_member_snapshot.sql"),
                (
                    snapshot_id, generator_version, configuration_version, str(manifest_path),
                    checksum, member_count, condition_count, utc_now(),
                ),
            )

    def current_members(self) -> list[dict]:
        return [
            {
                **dict(row),
                "outreach_consent": bool(row["outreach_consent"]),
                "last_contact_date": date.fromisoformat(row["last_contact_date"]),
            }
            for row in self.connection.execute(read_sql("queries/current_members.sql")).fetchall()
        ]

    def current_member_conditions(self) -> list[dict]:
        return [
            dict(row)
            for row in self.connection.execute(
                read_sql("queries/current_member_conditions.sql")
            ).fetchall()
        ]

    def protected_member_snapshot_ids(self) -> set[str]:
        return {
            row["member_snapshot_id"]
            for row in self.connection.execute(
                read_sql("queries/protected_member_snapshots.sql")
            ).fetchall()
        }

    def latest_member_snapshot_id(self) -> str | None:
        row = self.connection.execute(read_sql("queries/latest_member_snapshot.sql")).fetchone()
        return row["snapshot_id"] if row else None

    def delete_member_snapshot_records(self, snapshot_ids: list[str]) -> None:
        with self.connection:
            self.connection.executemany(
                read_sql("mutations/delete_member_snapshot.sql"),
                [(snapshot_id,) for snapshot_id in snapshot_ids],
            )

    def complete_run(self, run_id: str, status: str, counts: dict[str, int], error_message: str | None = None) -> None:
        now = utc_now()
        with self.connection:
            self.connection.execute(
                read_sql("mutations/complete_run.sql"),
                (
                    now, status, now, status, counts["extracted"], counts["valid"], counts["invalid"],
                    counts["published"], counts.get("inserted", 0), counts.get("updated", 0),
                    counts.get("unchanged", 0), counts.get("rejected", counts["invalid"]),
                    error_message, run_id,
                ),
            )

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
            self.connection.execute(
                read_sql("mutations/record_readiness.sql"),
                (
                    run_id, source, city_id, now, now, records, records - rejected, rejected,
                    inserted, updated, unchanged, rejected, latest,
                ),
            )

    def record_extraction_metrics(self, run_id: str, metrics: list[dict]) -> None:
        with self.connection:
            self.connection.executemany(
                read_sql("mutations/record_extraction_metric.sql"),
                [
                    (
                        run_id, metric["source"], metric["city_id"], metric["duration_ms"],
                        metric["attempts"], metric["http_status"], metric["response_bytes"],
                        metric["status"], utc_now(),
                    )
                    for metric in metrics
                ],
            )

    def record_raw_manifest(self, manifest: dict) -> None:
        with self.connection:
            self.connection.execute(
                read_sql("mutations/record_raw_manifest.sql"),
                (
                    manifest["run_id"], manifest["source"], manifest["city_id"],
                    manifest["file_path"], manifest["manifest_path"], manifest["content_hash"],
                    manifest["file_checksum"], manifest["row_count"], manifest["minimum_timestamp"],
                    manifest["maximum_timestamp"], manifest["reused_from_run_id"],
                    manifest["published_at"], manifest.get("artifact_type", "city_snapshot"),
                    manifest.get("schema_version"), manifest.get("schema_fingerprint"),
                    manifest.get("file_size_bytes"), manifest.get("row_group_count"),
                    manifest.get("input_file_count"),
                ),
            )

    def latest_raw_manifest(self, source: str, city_id: str) -> sqlite3.Row | None:
        return self.connection.execute(
            read_sql("queries/latest_raw_manifest.sql"), (source, city_id)
        ).fetchone()

    def record_failure(self, run_id: str, source: str, city_id: str, message: str) -> None:
        with self.connection:
            self.connection.execute(
                read_sql("mutations/record_failure.sql"),
                (run_id, source, city_id, utc_now(), message),
            )

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
        with self.connection:
            self.connection.execute(
                read_sql("mutations/quarantine_record.sql"),
                (
                    run_id, source, city_id, type(error).__name__, field_name, str(error),
                    json.dumps(payload, default=str), utc_now(), natural_key,
                    json.dumps(invalid_value, default=str), severity, "v1",
                ),
            )

    def quarantine_issues(
        self,
        run_id: str,
        source: str,
        city_id: str,
        issues: list[ValidationIssue],
    ) -> None:
        with self.connection:
            self.connection.executemany(
                read_sql("mutations/quarantine_record.sql"),
                [
                    (
                        run_id, source, city_id, issue.error_type, issue.field_name,
                        issue.error_message, json.dumps(issue.record_payload, default=str), utc_now(),
                        issue.natural_key, json.dumps(issue.invalid_value, default=str),
                        issue.severity, "v1",
                    )
                    for issue in issues
                ],
            )

    def record_dataset(self, run_id: str, name: str, path: Path, count: int) -> None:
        with self.connection:
            self.connection.execute(
                read_sql("mutations/record_dataset.sql"),
                (run_id, name, str(path), count, utc_now()),
            )

    def upsert_watermark(self, run_id: str, source: str, city_id: str, watermark_type: str, value: str) -> None:
        with self.connection:
            self.connection.execute(
                read_sql("mutations/upsert_watermark.sql"),
                (source, city_id, watermark_type, value, run_id, utc_now()),
            )

    def watermark(self, source: str, city_id: str, watermark_type: str) -> str | None:
        row = self.connection.execute(
            read_sql("queries/get_watermark.sql"),
            (source, city_id, watermark_type),
        ).fetchone()
        return row["watermark_value"] if row else None

    def latest_published_run(self) -> sqlite3.Row | None:
        return self.connection.execute(read_sql("queries/latest_published_run.sql")).fetchone()

    def query(self, relative_path: str, parameters: tuple = ()) -> list[sqlite3.Row]:
        return self.connection.execute(read_sql(relative_path), parameters).fetchall()
