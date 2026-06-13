import asyncio
import logging
import os
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq
import duckdb

from src.clients.nasa_power import NasaPowerClient
from src.clients.open_meteo import OpenMeteoClient
from src.config import ROOT, load_cities, load_rules
from src.metadata import MetadataStore
from src.pipeline.marts import build_marts
from src.quality import run_quality_checks
from src.rules import compile_rules
from src.storage import write_models, write_rows
from src.synthetic import generate_members, member_reference_version
from src.sql import render_sql


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("caresignal")
RETENTION_RUNS = 5


def latest_timestamp(records: list) -> str | None:
    values = [
        getattr(record, "observed_at", None) or getattr(record, "observed_date", None)
        for record in records
    ]
    values = [value for value in values if value is not None]
    return max(values).isoformat() if values else None


def ensure_references() -> tuple[Path, Path, str, str]:
    cities = load_cities()
    member_version = member_reference_version(cities)
    member_root = ROOT / f"data/reference/synthetic_members/version={member_version}"
    member_files = [member_root / "members.parquet", member_root / "member_conditions.parquet"]
    if not all(path.exists() for path in member_files):
        members, conditions = generate_members(cities)
        write_rows(member_root / "members.parquet", members)
        write_rows(member_root / "member_conditions.parquet", conditions)

    definitions, predicates, conditions = compile_rules(load_rules())
    ruleset_version = definitions[0]["ruleset_version"]
    rules_root = ROOT / f"data/reference/regional_rules/ruleset_version={ruleset_version}"
    rule_files = [
        rules_root / "rule_definitions.parquet",
        rules_root / "rule_predicates.parquet",
        rules_root / "rule_conditions.parquet",
    ]
    if not all(path.exists() for path in rule_files):
        write_rows(rules_root / "rule_definitions.parquet", definitions)
        write_rows(rules_root / "rule_predicates.parquet", predicates)
        write_rows(rules_root / "rule_conditions.parquet", conditions)
    return member_root, rules_root, member_version, ruleset_version


async def extract_forecasts(run_id: str, metadata: MetadataStore) -> int:
    cities = load_cities()
    total = 0
    async with OpenMeteoClient() as client:
        weather_results, air_results = await asyncio.gather(
            asyncio.gather(*(client.fetch_weather(city) for city in cities), return_exceptions=True),
            asyncio.gather(*(client.fetch_air_quality(city) for city in cities), return_exceptions=True),
        )
    for source, results in [("open_meteo_weather", weather_results), ("open_meteo_air_quality", air_results)]:
        for city, result in zip(cities, results, strict=True):
            if isinstance(result, Exception):
                metadata.record_failure(run_id, source, city.city_id, str(result))
                metadata.quarantine(run_id, source, city.city_id, result, {"city_id": city.city_id})
                raise result
            count = write_models(ROOT / f"data/raw/source={source}/run_id={run_id}/{city.city_id}.parquet", result)
            metadata.record_readiness(run_id, source, city.city_id, count, latest_timestamp(result))
            total += count
    return total


async def ensure_history(run_id: str, metadata: MetadataStore, baseline_end_year: int) -> int:
    cities = load_cities()
    history_root = ROOT / f"data/raw/source=nasa_power_daily/schema_version=v2/baseline_end_year={baseline_end_year}"
    missing = [city for city in cities if not any((history_root / f"city_id={city.city_id}").glob("year=*/*.parquet"))]
    cached = [city for city in cities if city not in missing]
    for city in cached:
        metadata.record_readiness(run_id, "nasa_power_daily", city.city_id, 0, f"{baseline_end_year}-12-31")
    if not missing:
        return 0

    start, end = date(baseline_end_year - 4, 1, 1), date(baseline_end_year, 12, 31)
    async with NasaPowerClient() as client:
        results = await asyncio.gather(
            *(client.fetch_daily_history(city, start, end) for city in missing),
            return_exceptions=True,
        )
    total = 0
    for city, result in zip(missing, results, strict=True):
        if isinstance(result, Exception):
            metadata.record_failure(run_id, "nasa_power_daily", city.city_id, str(result))
            metadata.quarantine(run_id, "nasa_power_daily", city.city_id, result, {"city_id": city.city_id})
            raise result
        by_year: dict[int, list] = {}
        for record in result:
            by_year.setdefault(record.observed_date.year, []).append(record)
        for year, records in by_year.items():
            total += write_models(history_root / f"city_id={city.city_id}/year={year}/data.parquet", records)
        metadata.record_readiness(run_id, "nasa_power_daily", city.city_id, len(result), latest_timestamp(result))
    return total


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
    member_root, rules_root, member_version, ruleset_version = ensure_references()
    metadata.start_run(run_id, ruleset_version, member_version, baseline_end_year)
    counts = {"extracted": 0, "valid": 0, "invalid": 0, "published": 0}
    staging = ROOT / f"data/processed/.staging-{run_id}"
    LOGGER.info("Starting run_id=%s", run_id)
    try:
        counts["extracted"] += await extract_forecasts(run_id, metadata)
        counts["extracted"] += await ensure_history(run_id, metadata, baseline_end_year)
        counts["valid"] = counts["extracted"]

        quality_results = run_quality_checks(run_id, str(ROOT / "data/raw"))
        write_models(staging / "quality_results.parquet", quality_results)
        if any(result.status == "fail" for result in quality_results):
            raise RuntimeError("Fatal data quality failure")

        build_marts(ROOT, run_id, processed=staging, members_root=member_root, rules_root=rules_root)
        verify_publication(staging)
        counts["published"] = publish_run(run_id, staging, metadata)
        for city in load_cities():
            metadata.upsert_watermark(run_id, "open_meteo_weather", city.city_id, "latest_successful_run", run_id)
            metadata.upsert_watermark(run_id, "open_meteo_air_quality", city.city_id, "latest_successful_run", run_id)
            metadata.upsert_watermark(run_id, "nasa_power_daily", city.city_id, "baseline_end_year", str(baseline_end_year))
        metadata.complete_run(run_id, "success", counts)
        apply_retention()
        LOGGER.info("Completed run_id=%s", run_id)
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
