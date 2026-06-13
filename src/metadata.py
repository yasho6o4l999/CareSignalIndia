import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import ROOT


DATABASE_PATH = ROOT / "data/metadata/pipeline.db"
SQLITE_ROOT = ROOT / "sql/sqlite"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_sql(relative_path: str) -> str:
    return (SQLITE_ROOT / relative_path).read_text(encoding="utf-8")


class MetadataStore:
    def __init__(self, path: Path = DATABASE_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
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
    ) -> None:
        with self.connection:
            self.connection.execute(
                read_sql("mutations/start_run.sql"),
                (run_id, utc_now(), ruleset_version, member_version, baseline_end_year, configuration_version),
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

    def record_failure(self, run_id: str, source: str, city_id: str, message: str) -> None:
        with self.connection:
            self.connection.execute(
                read_sql("mutations/record_failure.sql"),
                (run_id, source, city_id, utc_now(), message),
            )

    def quarantine(self, run_id: str, source: str, city_id: str | None, error: Exception, payload: Any) -> None:
        with self.connection:
            self.connection.execute(
                read_sql("mutations/quarantine_record.sql"),
                (run_id, source, city_id, type(error).__name__, str(error), json.dumps(payload, default=str), utc_now()),
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
