import argparse
import asyncio
import json
from datetime import date

from src.clients.nasa_power import NasaPowerClient
from src.clients.open_meteo import OpenMeteoClient
from src.config import load_cities
from src.metadata import MetadataStore


async def retry_failed_sources(run_id: str) -> list[dict]:
    metadata = MetadataStore()
    targets = metadata.query("queries/failed_source_targets.sql", (run_id,))
    metadata.close()
    cities = {city.city_id: city for city in load_cities()}
    results: list[dict] = []

    forecast_targets = [target for target in targets if target["source"] != "nasa_power_daily"]
    async with OpenMeteoClient() as client:
        for target in forecast_targets:
            source, city_id = target["source"], target["city_id"]
            try:
                batch = (
                    await client.fetch_weather(cities[city_id])
                    if source == "open_meteo_weather"
                    else await client.fetch_air_quality(cities[city_id])
                )
                results.append({
                    "source": source, "city_id": city_id, "status": "recovered",
                    "valid_records": len(batch.records), "issues": len(batch.issues),
                })
            except Exception as error:
                results.append({
                    "source": source, "city_id": city_id, "status": "still_failed",
                    "error": str(error),
                })

    history_targets = [target for target in targets if target["source"] == "nasa_power_daily"]
    baseline_end_year = date.today().year - 1
    async with NasaPowerClient() as client:
        for target in history_targets:
            city_id = target["city_id"]
            try:
                batch = await client.fetch_daily_history(
                    cities[city_id],
                    date(baseline_end_year - 4, 1, 1),
                    date(baseline_end_year, 12, 31),
                )
                results.append({
                    "source": "nasa_power_daily", "city_id": city_id, "status": "recovered",
                    "valid_records": len(batch.records), "issues": len(batch.issues),
                })
            except Exception as error:
                results.append({
                    "source": "nasa_power_daily", "city_id": city_id, "status": "still_failed",
                    "error": str(error),
                })
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retry failed source-city calls diagnostically without publishing or advancing watermarks."
    )
    parser.add_argument("--run-id", required=True)
    arguments = parser.parse_args()
    results = asyncio.run(retry_failed_sources(arguments.run_id))
    print(json.dumps(results, indent=2))
    raise SystemExit(1 if any(result["status"] == "still_failed" for result in results) else 0)


if __name__ == "__main__":
    main()
