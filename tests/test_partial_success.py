from datetime import datetime, timezone

import duckdb
import pytest

import etl
from src.config import PublicationPolicy, load_cities
from src.models import AirQualityRecord, WeatherRecord
from src.readiness import evaluate_readiness
from src.sql import render_sql
from src.storage import write_rows


POLICY = PublicationPolicy(
    required_sources=["open_meteo_weather", "open_meteo_air_quality", "nasa_power_daily"],
    minimum_complete_cities=5,
    minimum_complete_city_ratio=0.70,
)


def test_readiness_supports_success_partial_success_and_failure() -> None:
    cities = {f"city-{number}" for number in range(7)}
    all_sources = {source: set(cities) for source in POLICY.required_sources}
    assert evaluate_readiness(cities, all_sources, POLICY).status == "success"

    all_sources["open_meteo_weather"] -= {"city-5", "city-6"}
    partial = evaluate_readiness(cities, all_sources, POLICY)
    assert partial.status == "partial_success"
    assert partial.minimum_required == 5
    assert partial.incomplete_cities == {"city-5", "city-6"}

    all_sources["open_meteo_air_quality"] -= {"city-4"}
    assert evaluate_readiness(cities, all_sources, POLICY).status == "failed"


@pytest.mark.asyncio
async def test_forecast_extraction_quarantines_one_city_failure_and_continues(tmp_path, monkeypatch) -> None:
    cities = load_cities()[:2]
    observed_at = datetime.now(timezone.utc)

    class FakeOpenMeteoClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def fetch_weather(self, city):
            if city.city_id == cities[0].city_id:
                raise RuntimeError("simulated weather outage")
            return [
                WeatherRecord(
                    city_id=city.city_id,
                    observed_at=observed_at,
                    apparent_temperature=35,
                    temperature_2m=34,
                    precipitation=0,
                    relative_humidity=50,
                    wind_speed=5,
                    extracted_at=observed_at,
                )
            ]

        async def fetch_air_quality(self, city):
            return [
                AirQualityRecord(
                    city_id=city.city_id,
                    observed_at=observed_at,
                    pm2_5=20,
                    pm10=30,
                    extracted_at=observed_at,
                )
            ]

    class FakeMetadata:
        failures = []
        readiness = []
        quarantined = []

        def record_failure(self, *args):
            self.failures.append(args)

        def record_readiness(self, *args):
            self.readiness.append(args)

        def quarantine(self, *args):
            self.quarantined.append(args)

    metadata = FakeMetadata()
    monkeypatch.setattr(etl, "ROOT", tmp_path)
    monkeypatch.setattr(etl, "load_cities", lambda: cities)
    monkeypatch.setattr(etl, "OpenMeteoClient", FakeOpenMeteoClient)

    result = await etl.extract_forecasts("run-1", metadata)

    assert result.failures == 1
    assert result.successful_cities_by_source["open_meteo_weather"] == {cities[1].city_id}
    assert result.successful_cities_by_source["open_meteo_air_quality"] == {city.city_id for city in cities}
    assert len(metadata.quarantined) == 1


def test_city_conditions_excludes_cities_outside_publication_set(tmp_path) -> None:
    observed_at = datetime(2099, 1, 1, tzinfo=timezone.utc)
    weather = [
        {
            "city_id": city_id,
            "observed_at": observed_at,
            "apparent_temperature": 35,
            "temperature_2m": 34,
            "precipitation": 0,
            "relative_humidity": 50,
            "wind_speed": 5,
        }
        for city_id in ["complete", "incomplete"]
    ]
    air = [
        {"city_id": city_id, "observed_at": observed_at, "pm2_5": 20, "pm10": 30}
        for city_id in ["complete", "incomplete"]
    ]
    write_rows(tmp_path / "weather.parquet", weather)
    write_rows(tmp_path / "air.parquet", air)
    write_rows(tmp_path / "publication_cities.parquet", [{"city_id": "complete"}])

    output = tmp_path / "city_conditions.parquet"
    duckdb.connect().execute(
        render_sql(
            "marts/build_city_conditions.sql",
            weather_path=tmp_path / "weather.parquet",
            air_path=tmp_path / "air.parquet",
            publication_cities_path=tmp_path / "publication_cities.parquet",
            output_path=output,
        )
    )

    assert duckdb.connect().execute(
        render_sql("common/count_rows.sql", dataset_path=output)
    ).fetchone()[0] == 1
