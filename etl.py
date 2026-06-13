import asyncio
import json
import logging
from datetime import datetime, timezone

from src.clients.open_meteo import OpenMeteoClient
from src.config import ROOT, load_cities, load_rules
from src.pipeline.marts import build_marts
from src.quality import run_quality_checks
from src.rules import compile_rules
from src.storage import write_models, write_rows
from src.synthetic import generate_members


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("caresignal")


async def extract(run_id: str) -> None:
    cities = load_cities()
    rules = load_rules()
    async with OpenMeteoClient() as client:
        weather_results, air_results = await asyncio.gather(
            asyncio.gather(*(client.fetch_weather(city) for city in cities)),
            asyncio.gather(*(client.fetch_air_quality(city) for city in cities)),
        )
    for city, records in zip(cities, weather_results, strict=True):
        write_models(ROOT / f"data/raw/source=open_meteo_weather/run_id={run_id}/{city.city_id}.parquet", records)
    for city, records in zip(cities, air_results, strict=True):
        write_models(ROOT / f"data/raw/source=open_meteo_air_quality/run_id={run_id}/{city.city_id}.parquet", records)

    members, conditions = generate_members(cities)
    synthetic_root = ROOT / f"data/raw/source=synthetic_members/run_id={run_id}"
    write_rows(synthetic_root / "members.parquet", members)
    write_rows(synthetic_root / "member_conditions.parquet", conditions)

    rule_definitions, rule_conditions = compile_rules(rules)
    rules_root = ROOT / f"data/raw/source=regional_rules/run_id={run_id}"
    write_rows(rules_root / "rule_definitions.parquet", rule_definitions)
    write_rows(rules_root / "rule_conditions.parquet", rule_conditions)


async def main() -> None:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    LOGGER.info("Starting run_id=%s", run_id)
    await extract(run_id)
    quality_results = run_quality_checks(run_id, str(ROOT / "data/raw"))
    quality_path = ROOT / f"data/processed/run_id={run_id}/quality_results.parquet"
    write_models(quality_path, quality_results)
    if any(result.status == "fail" for result in quality_results):
        raise RuntimeError(f"Fatal data quality failure; inspect {quality_path}")
    build_marts(ROOT, run_id)
    manifest = {
        "run_id": run_id,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "status": "success",
    }
    latest = ROOT / "data/processed/latest_run.json"
    latest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    LOGGER.info("Completed run_id=%s", run_id)


if __name__ == "__main__":
    asyncio.run(main())
