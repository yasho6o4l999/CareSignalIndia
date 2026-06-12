import asyncio
import random
from datetime import datetime, timezone

import httpx

from src.config import City
from src.models import AirQualityRecord, WeatherRecord


TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


class OpenMeteoClient:
    def __init__(self, concurrency: int = 4, attempts: int = 4) -> None:
        self._semaphore = asyncio.Semaphore(concurrency)
        self._attempts = attempts
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency),
            headers={"User-Agent": "CareSignal-India-Candidate-Assignment/0.1"},
        )

    async def __aenter__(self) -> "OpenMeteoClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.aclose()

    async def _get_json(self, url: str, params: dict) -> dict:
        async with self._semaphore:
            for attempt in range(1, self._attempts + 1):
                try:
                    response = await self._client.get(url, params=params)
                    if response.status_code in TRANSIENT_STATUS_CODES:
                        raise httpx.HTTPStatusError("transient response", request=response.request, response=response)
                    response.raise_for_status()
                    return response.json()
                except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError):
                    if attempt == self._attempts:
                        raise
                    await asyncio.sleep((2 ** (attempt - 1)) + random.random())
        raise RuntimeError("request attempts exhausted")

    async def fetch_weather(self, city: City) -> list[WeatherRecord]:
        payload = await self._get_json(
            "https://api.open-meteo.com/v1/forecast",
            {
                "latitude": city.latitude,
                "longitude": city.longitude,
                "hourly": "apparent_temperature,precipitation,relative_humidity_2m,wind_speed_10m",
                "forecast_days": 7,
                "timezone": "UTC",
            },
        )
        hourly = payload["hourly"]
        extracted_at = datetime.now(timezone.utc)
        return [
            WeatherRecord(
                city_id=city.city_id,
                observed_at=datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc),
                apparent_temperature=hourly["apparent_temperature"][index],
                precipitation=hourly["precipitation"][index],
                relative_humidity=hourly["relative_humidity_2m"][index],
                wind_speed=hourly["wind_speed_10m"][index],
                extracted_at=extracted_at,
            )
            for index, timestamp in enumerate(hourly["time"])
        ]

    async def fetch_air_quality(self, city: City) -> list[AirQualityRecord]:
        payload = await self._get_json(
            "https://air-quality-api.open-meteo.com/v1/air-quality",
            {
                "latitude": city.latitude,
                "longitude": city.longitude,
                "hourly": "pm2_5,pm10",
                "forecast_days": 7,
                "timezone": "UTC",
            },
        )
        hourly = payload["hourly"]
        extracted_at = datetime.now(timezone.utc)
        records: list[AirQualityRecord] = []
        for index, timestamp in enumerate(hourly["time"]):
            pm2_5 = hourly["pm2_5"][index]
            pm10 = hourly["pm10"][index]
            if pm2_5 is None or pm10 is None:
                continue
            records.append(
                AirQualityRecord(
                city_id=city.city_id,
                observed_at=datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc),
                pm2_5=pm2_5,
                pm10=pm10,
                extracted_at=extracted_at,
            )
            )
        return records
