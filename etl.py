import asyncio
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pyarrow.parquet as pq
import duckdb

from src.clients.nasa_power import NasaPowerClient
from src.clients.open_meteo import OpenMeteoClient
from src.config import (
    ROOT,
    configuration_version,
    load_cities,
    load_incremental_policy,
    load_extraction_policy,
    load_outreach_policy,
    load_publication_policy,
    load_rules,
    load_runtime_settings,
)
from src.incremental import ChangeMetrics, merge_forecast_snapshot
from src.metadata import MetadataStore
from src.pipeline.marts import build_marts
from src.quality import run_quality_checks
from src.readiness import evaluate_readiness
from src.raw import publish_forecast_snapshot
from src.reference import (
    MANIFEST_NAME,
    apply_member_snapshot_retention,
    member_snapshot_id,
    publish_member_snapshot,
    verify_member_snapshot,
)
from src.rules import compile_rules
from src.storage import write_models, write_rows
from src.synthetic import generate_members, member_reference_version
from src.sql import render_sql
from src.validation import ValidatedBatch


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("caresignal")
RETENTION_RUNS = 5


@dataclass
class ExtractionResult:
    records: int = 0
    failures: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    rejected: int = 0
    successful_cities_by_source: dict[str, set[str]] = field(default_factory=dict)
    latest_source_timestamps: dict[str, dict[str, str]] = field(default_factory=dict)

    def record_success(
        self,
        source: str,
        city_id: str,
        records: int,
        metrics: ChangeMetrics | None = None,
        latest: str | None = None,
    ) -> None:
        self.records += records
        if metrics:
            self.inserted += metrics.inserted
            self.updated += metrics.updated
            self.unchanged += metrics.unchanged
            self.rejected += metrics.rejected
        self.successful_cities_by_source.setdefault(source, set()).add(city_id)
        if latest:
            self.latest_source_timestamps.setdefault(source, {})[city_id] = latest

    def merge(self, other: "ExtractionResult") -> None:
        self.records += other.records
        self.failures += other.failures
        self.inserted += other.inserted
        self.updated += other.updated
        self.unchanged += other.unchanged
        self.rejected += other.rejected
        for source, cities in other.successful_cities_by_source.items():
            self.successful_cities_by_source.setdefault(source, set()).update(cities)
        for source, timestamps in other.latest_source_timestamps.items():
            self.latest_source_timestamps.setdefault(source, {}).update(timestamps)


def latest_timestamp(records: list) -> str | None:
    values = [
        getattr(record, "observed_at", None) or getattr(record, "observed_date", None)
        for record in records
    ]
    values = [value for value in values if value is not None]
    return max(values).isoformat() if values else None


def accepted_records(
    run_id: str,
    source: str,
    city_id: str,
    result: list | ValidatedBatch,
    metadata: MetadataStore,
) -> tuple[list, int, int]:
    if not isinstance(result, ValidatedBatch):
        return result, len(result), 0
    metadata.quarantine_issues(run_id, source, city_id, result.issues)
    policy = load_extraction_policy().sources[source]
    if (
        len(result.records) < policy.minimum_records
        or
        result.valid_ratio < policy.minimum_valid_record_ratio
        or result.invalid_records > policy.maximum_invalid_records
    ):
        raise ValueError(
            f"Record validation policy failed: valid_records={len(result.records)}, "
            f"valid_ratio={result.valid_ratio:.3f}, "
            f"invalid_records={result.invalid_records}"
        )
    return result.records, result.received_records, result.invalid_records


def ensure_references(
    metadata: MetadataStore,
    config_version: str,
    sync_id: str,
) -> tuple[Path, Path, str, str, str]:
    cities = load_cities()
    member_policy = load_runtime_settings().synthetic_members
    member_version = member_reference_version(cities, member_policy)
    members, member_conditions = generate_members(
        cities,
        count=member_policy.member_count,
        seed=member_policy.seed,
        city_weights=member_policy.city_weights,
        anchor_date=member_policy.anchor_date,
    )
    previous_snapshot_id = metadata.latest_member_snapshot_id()
    sync_metrics = metadata.reconcile_members(members, member_conditions, sync_id)
    members = metadata.current_members()
    member_conditions = metadata.current_member_conditions()
    snapshot_id = member_snapshot_id(member_version, members, member_conditions)
    previous_root = (
        ROOT / f"data/reference/member_snapshots/snapshot_id={previous_snapshot_id}"
        if previous_snapshot_id else None
    )
    member_root, member_manifest, member_manifest_checksum = publish_member_snapshot(
        ROOT / "data/reference/member_snapshots",
        snapshot_id,
        config_version,
        members,
        member_conditions,
        previous_root=previous_root,
        changed_cities=sync_metrics.changed_cities,
    )
    verify_member_snapshot(member_root)
    metadata.register_member_snapshot(
        snapshot_id,
        members[0]["generator_version"],
        member_manifest["configuration_version"],
        member_root / MANIFEST_NAME,
        member_manifest_checksum,
        member_manifest["member_count"],
        member_manifest["condition_count"],
    )

    definitions, predicates, conditions, severity_bands = compile_rules(load_rules())
    ruleset_version = definitions[0]["ruleset_version"]
    rules_root = ROOT / f"data/reference/regional_rules/ruleset_version={ruleset_version}"
    rule_files = [
        rules_root / "rule_definitions.parquet",
        rules_root / "rule_predicates.parquet",
        rules_root / "rule_conditions.parquet",
        rules_root / "rule_severity_bands.parquet",
    ]
    if not all(path.exists() for path in rule_files):
        write_rows(rules_root / "rule_definitions.parquet", definitions)
        write_rows(rules_root / "rule_predicates.parquet", predicates)
        write_rows(rules_root / "rule_conditions.parquet", conditions)
        write_rows(rules_root / "rule_severity_bands.parquet", severity_bands)
    return member_root, rules_root, member_version, snapshot_id, ruleset_version


def record_source_failure(
    metadata: MetadataStore,
    run_id: str,
    source: str,
    city_id: str,
    error: Exception,
) -> None:
    metadata.record_failure(run_id, source, city_id, str(error))
    metadata.quarantine(run_id, source, city_id, error, {"city_id": city_id})
    LOGGER.warning("Source failure source=%s city_id=%s error=%s", source, city_id, error)


async def extract_forecasts(run_id: str, metadata: MetadataStore) -> ExtractionResult:
    cities = load_cities()
    extraction = ExtractionResult()
    cutoff = datetime.now(timezone.utc) - timedelta(
        hours=load_incremental_policy().forecast_correction_lookback_hours
    )
    async with OpenMeteoClient() as client:
        weather_results, air_results = await asyncio.gather(
            asyncio.gather(*(client.fetch_weather(city) for city in cities), return_exceptions=True),
            asyncio.gather(*(client.fetch_air_quality(city) for city in cities), return_exceptions=True),
        )
    if hasattr(metadata, "record_extraction_metrics"):
        metadata.record_extraction_metrics(run_id, client.metrics)
    for source, results in [("open_meteo_weather", weather_results), ("open_meteo_air_quality", air_results)]:
        for city, result in zip(cities, results, strict=True):
            if isinstance(result, Exception):
                record_source_failure(metadata, run_id, source, city.city_id, result)
                extraction.failures += 1
                extraction.rejected += 1
                continue
            try:
                result, received_records, validation_rejections = accepted_records(
                    run_id, source, city.city_id, result, metadata
                )
            except Exception as error:
                record_source_failure(metadata, run_id, source, city.city_id, error)
                extraction.failures += 1
                extraction.rejected += 1
                continue
            output_path = ROOT / f"data/raw/source={source}/run_id={run_id}/{city.city_id}.parquet"
            previous_run = metadata.watermark(source, city.city_id, "latest_successful_run")
            previous_path = (
                ROOT / f"data/raw/source={source}/run_id={previous_run}/{city.city_id}.parquet"
                if previous_run else None
            )
            metrics, manifest = publish_forecast_snapshot(
                source,
                city.city_id,
                run_id,
                result,
                previous_path,
                previous_run,
                output_path,
                cutoff,
            )
            if hasattr(metadata, "record_raw_manifest"):
                metadata.record_raw_manifest(manifest)
            latest = latest_timestamp(result)
            metadata.record_readiness(
                run_id,
                source,
                city.city_id,
                received_records,
                latest,
                metrics.inserted,
                metrics.updated,
                metrics.unchanged,
                metrics.rejected + validation_rejections,
            )
            metrics = ChangeMetrics(
                metrics.inserted, metrics.updated, metrics.unchanged,
                metrics.rejected + validation_rejections,
            )
            extraction.record_success(source, city.city_id, received_records, metrics, latest)
    return extraction


async def ensure_history(run_id: str, metadata: MetadataStore, baseline_end_year: int) -> ExtractionResult:
    cities = load_cities()
    extraction = ExtractionResult()
    history_root = ROOT / f"data/raw/source=nasa_power_daily/schema_version=v2/baseline_end_year={baseline_end_year}"
    missing = [city for city in cities if not any((history_root / f"city_id={city.city_id}").glob("year=*/*.parquet"))]
    cached = [city for city in cities if city not in missing]
    for city in cached:
        metadata.record_readiness(run_id, "nasa_power_daily", city.city_id, 0, f"{baseline_end_year}-12-31")
        extraction.record_success("nasa_power_daily", city.city_id, 0, latest=f"{baseline_end_year}-12-31")
    if not missing:
        return extraction

    start, end = date(baseline_end_year - 4, 1, 1), date(baseline_end_year, 12, 31)
    async with NasaPowerClient() as client:
        results = await asyncio.gather(
            *(client.fetch_daily_history(city, start, end) for city in missing),
            return_exceptions=True,
        )
    metadata.record_extraction_metrics(run_id, client.metrics)
    for city, result in zip(missing, results, strict=True):
        if isinstance(result, Exception):
            record_source_failure(metadata, run_id, "nasa_power_daily", city.city_id, result)
            extraction.failures += 1
            extraction.rejected += 1
            continue
        try:
            result, received_records, validation_rejections = accepted_records(
                run_id, "nasa_power_daily", city.city_id, result, metadata
            )
        except Exception as error:
            record_source_failure(metadata, run_id, "nasa_power_daily", city.city_id, error)
            extraction.failures += 1
            extraction.rejected += 1
            continue
        by_year: dict[int, list] = {}
        for record in result:
            by_year.setdefault(record.observed_date.year, []).append(record)
        for year, records in by_year.items():
            extraction.records += write_models(history_root / f"city_id={city.city_id}/year={year}/data.parquet", records)
        latest = latest_timestamp(result)
        metadata.record_readiness(
            run_id,
            "nasa_power_daily",
            city.city_id,
            received_records,
            latest,
            inserted=len(result),
            rejected=validation_rejections,
        )
        extraction.record_success(
            "nasa_power_daily",
            city.city_id,
            0,
            ChangeMetrics(inserted=len(result), updated=0, unchanged=0, rejected=validation_rejections),
            latest,
        )
    return extraction


def parquet_count(path: Path) -> int:
    return pq.ParquetFile(path).metadata.num_rows


def publish_run(run_id: str, staging: Path, metadata: MetadataStore) -> int:
    final = ROOT / f"data/processed/run_id={run_id}"
    os.replace(staging, final)
    total = 0
    for path in sorted(final.glob("*.parquet")):
        count = parquet_count(path)
        metadata.record_dataset(run_id, path.stem, path, count)
        total += count
    return total


def verify_publication(staging: Path) -> None:
    expected = {
        "quality_results.parquet",
        "historical_baselines.parquet",
        "city_conditions.parquet",
        "active_triggers.parquet",
        "outreach_queue.parquet",
        "stakeholder_alerts.parquet",
        "publication_cities.parquet",
    }
    missing = expected - {path.name for path in staging.glob("*.parquet")}
    if missing:
        raise RuntimeError(f"Missing publication datasets: {sorted(missing)}")
    consent, duplicates, persistence = duckdb.connect().execute(
        render_sql(
            "quality/publication_contract.sql",
            outreach_queue_path=staging / "outreach_queue.parquet",
            active_triggers_path=staging / "active_triggers.parquet",
        )
    ).fetchone()
    if any((consent, duplicates, persistence)):
        raise RuntimeError(
            f"Publication contract failed: consent={consent}, duplicates={duplicates}, persistence={persistence}"
        )


def apply_retention() -> None:
    for parent, pattern in [(ROOT / "data/processed", "run_id=*"), (ROOT / "data/raw/source=open_meteo_weather", "run_id=*"), (ROOT / "data/raw/source=open_meteo_air_quality", "run_id=*")]:
        runs = sorted(parent.glob(pattern), reverse=True)
        for stale in runs[RETENTION_RUNS:]:
            shutil.rmtree(stale)


async def main() -> None:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    baseline_end_year = date.today().year - 1
    metadata = MetadataStore()
    config_version = configuration_version()
    member_root, rules_root, member_version, member_snapshot, ruleset_version = ensure_references(
        metadata, config_version, run_id
    )
    metadata.start_run(
        run_id,
        ruleset_version,
        member_version,
        baseline_end_year,
        config_version,
        member_snapshot,
    )
    counts = {
        "extracted": 0, "valid": 0, "invalid": 0, "published": 0,
        "inserted": 0, "updated": 0, "unchanged": 0, "rejected": 0,
    }
    staging = ROOT / f"data/processed/.staging-{run_id}"
    LOGGER.info("Starting run_id=%s", run_id)
    try:
        extraction = await extract_forecasts(run_id, metadata)
        extraction.merge(await ensure_history(run_id, metadata, baseline_end_year))
        counts["extracted"] = extraction.records
        counts["invalid"] = extraction.rejected
        duplicate_rejections = max(0, extraction.rejected - extraction.failures)
        counts["valid"] = counts["extracted"] - duplicate_rejections
        counts["inserted"] = extraction.inserted
        counts["updated"] = extraction.updated
        counts["unchanged"] = extraction.unchanged
        counts["rejected"] = extraction.rejected
        cities = load_cities()
        readiness = evaluate_readiness(
            {city.city_id for city in cities},
            extraction.successful_cities_by_source,
            load_publication_policy(),
            {city.city_id: set(city.expected_sources) for city in cities},
            extraction.latest_source_timestamps,
        )
        if readiness.status == "failed":
            raise RuntimeError(f"Publication readiness failed: {readiness.summary}")

        quality_results = run_quality_checks(run_id, str(ROOT / "data/raw"), len(readiness.complete_cities))
        write_models(staging / "quality_results.parquet", quality_results)
        if any(result.status == "fail" for result in quality_results):
            raise RuntimeError("Fatal data quality failure")

        publication_cities = staging / "publication_cities.parquet"
        write_rows(publication_cities, [{"city_id": city_id} for city_id in sorted(readiness.complete_cities)])
        build_marts(
            ROOT,
            run_id,
            processed=staging,
            members_root=member_root,
            rules_root=rules_root,
            publication_cities=publication_cities,
            cooldown_hours=load_outreach_policy().cooldown_hours,
        )
        verify_publication(staging)
        counts["published"] = publish_run(run_id, staging, metadata)
        for source, successful_cities in extraction.successful_cities_by_source.items():
            for city_id in successful_cities:
                watermark_type = "baseline_end_year" if source == "nasa_power_daily" else "latest_successful_run"
                value = str(baseline_end_year) if source == "nasa_power_daily" else run_id
                metadata.upsert_watermark(run_id, source, city_id, watermark_type, value)
        run_message = readiness.summary if readiness.status == "partial_success" else None
        metadata.complete_run(run_id, readiness.status, counts, run_message)
        apply_retention()
        removed_snapshots = apply_member_snapshot_retention(
            ROOT / "data/reference/member_snapshots",
            metadata.protected_member_snapshot_ids(),
            load_runtime_settings().synthetic_members.snapshot_retention_count,
        )
        metadata.delete_member_snapshot_records(removed_snapshots)
        LOGGER.info("Completed run_id=%s status=%s %s", run_id, readiness.status, readiness.summary)
    except Exception as error:
        if staging.exists():
            shutil.rmtree(staging)
        metadata.complete_run(run_id, "failed", counts, str(error))
        LOGGER.exception("Failed run_id=%s", run_id)
        raise
    finally:
        metadata.close()


if __name__ == "__main__":
    asyncio.run(main())
