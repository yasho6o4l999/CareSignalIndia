import asyncio
import random
from datetime import date, datetime, timezone

import httpx

from src.config import City
from src.models import HistoricalWeatherRecord


TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
MISSING_VALUE = -999.0


class NasaPowerClient:
    def __init__(self, concurrency: int = 2, attempts: int = 4) -> None:
        self._semaphore = asyncio.Semaphore(concurrency)
        self._attempts = attempts
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(90.0),
            limits=httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency),
            headers={"User-Agent": "CareSignal-India-Candidate-Assignment/0.1"},
        )

    async def __aenter__(self) -> "NasaPowerClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.aclose()

    async def _get_json(self, params: dict) -> dict:
        async with self._semaphore:
            for attempt in range(1, self._attempts + 1):
                try:
                    response = await self._client.get(
                        "https://power.larc.nasa.gov/api/temporal/daily/point",
                        params=params,
                    )
                    if response.status_code in TRANSIENT_STATUS_CODES:
                        raise httpx.HTTPStatusError("transient response", request=response.request, response=response)
                    response.raise_for_status()
                    return response.json()
                except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError):
                    if attempt == self._attempts:
                        raise
                    await asyncio.sleep((2 ** (attempt - 1)) + random.random())
        raise RuntimeError("request attempts exhausted")

    async def fetch_daily_history(self, city: City, start: date, end: date) -> list[HistoricalWeatherRecord]:
        payload = await self._get_json(
            {
                "parameters": "T2M_MAX,T2M_MIN,PRECTOTCORR",
                "community": "SB",
                "longitude": city.longitude,
                "latitude": city.latitude,
                "start": start.strftime("%Y%m%d"),
                "end": end.strftime("%Y%m%d"),
                "format": "JSON",
                "time-standard": "UTC",
            }
        )
        parameters = payload["properties"]["parameter"]
        temperature = parameters["T2M_MAX"]
        minimum_temperature = parameters["T2M_MIN"]
        precipitation = parameters["PRECTOTCORR"]
        extracted_at = datetime.now(timezone.utc)
        records: list[HistoricalWeatherRecord] = []
        for date_key, temperature_value in temperature.items():
            precipitation_value = precipitation.get(date_key)
            minimum_temperature_value = minimum_temperature.get(date_key)
            if (
                temperature_value == MISSING_VALUE
                or minimum_temperature_value in (None, MISSING_VALUE)
                or precipitation_value in (None, MISSING_VALUE)
            ):
                continue
            records.append(
                HistoricalWeatherRecord(
                    city_id=city.city_id,
                    observed_date=datetime.strptime(date_key, "%Y%m%d").replace(tzinfo=timezone.utc),
                    temperature_2m=temperature_value,
                    minimum_temperature_2m=minimum_temperature_value,
                    temperature_range=temperature_value - minimum_temperature_value,
                    precipitation=precipitation_value,
                    extracted_at=extracted_at,
                )
            )
        return records
