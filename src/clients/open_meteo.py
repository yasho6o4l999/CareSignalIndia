import asyncio
import random
import time
from datetime import datetime, timezone

import httpx

from src.config import City, ExtractionSourcePolicy, load_extraction_policy
from src.contracts import validate_parallel_arrays, validate_time_series
from src.models import AirQualityRecord, WeatherRecord
from src.validation import (
    ValidatedBatch,
    ValidationIssue,
    cross_field_warnings,
    source_utc_timestamp,
    validate_record,
)


TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


class OpenMeteoClient:
    def __init__(
        self,
        concurrency: int | None = None,
        attempts: int | None = None,
        policies: dict[str, ExtractionSourcePolicy] | None = None,
    ) -> None:
        policies = policies or load_extraction_policy().sources
        self._policies = policies
        max_concurrency = max(policy.maximum_concurrency for policy in policies.values())
        concurrency = concurrency or max_concurrency
        self._semaphore = asyncio.Semaphore(concurrency)
        self._semaphores = {
            source: asyncio.Semaphore(
                concurrency if concurrency != max_concurrency else policy.maximum_concurrency
            )
            for source, policy in policies.items()
        }
        self.metrics: list[dict] = []
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(max(policy.timeout_seconds for policy in policies.values())),
            limits=httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency),
            headers={"User-Agent": "CareSignal-India-Candidate-Assignment/0.1"},
        )

    async def __aenter__(self) -> "OpenMeteoClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.aclose()

    async def _get_json(self, source: str, city_id: str, url: str, params: dict) -> dict:
        policy = self._policies[source]
        started = time.perf_counter()
        status_code = None
        response_bytes = 0
        async with self._semaphores[source]:
            for attempt in range(1, policy.maximum_attempts + 1):
                try:
                    response = await self._client.get(
                        url, params=params, timeout=policy.timeout_seconds
                    )
                    status_code = response.status_code
                    response_bytes = len(response.content)
                    if response.status_code in TRANSIENT_STATUS_CODES:
                        raise httpx.HTTPStatusError("transient response", request=response.request, response=response)
                    response.raise_for_status()
                    payload = response.json()
                    self.metrics.append(
                        {
                            "source": source, "city_id": city_id, "duration_ms": round((time.perf_counter() - started) * 1000),
                            "attempts": attempt, "http_status": status_code, "response_bytes": response_bytes,
                            "status": "success",
                        }
                    )
                    return payload
                except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as error:
                    retryable = not isinstance(error, httpx.HTTPStatusError) or (
                        error.response.status_code in TRANSIENT_STATUS_CODES
                    )
                    if attempt == policy.maximum_attempts or not retryable:
                        self.metrics.append(
                            {
                                "source": source, "city_id": city_id, "duration_ms": round((time.perf_counter() - started) * 1000),
                                "attempts": attempt, "http_status": status_code, "response_bytes": response_bytes,
                                "status": "failed",
                            }
                        )
                        raise
                    retry_after = (
                        response.headers.get("Retry-After")
                        if status_code == 429 and "response" in locals()
                        else None
                    )
                    await asyncio.sleep(float(retry_after) if retry_after else (2 ** (attempt - 1)) + random.random())
                except ValueError:
                    self.metrics.append(
                        {
                            "source": source, "city_id": city_id,
                            "duration_ms": round((time.perf_counter() - started) * 1000),
                            "attempts": attempt, "http_status": status_code,
                            "response_bytes": response_bytes, "status": "invalid_json",
                        }
                    )
                    raise
        raise RuntimeError("request attempts exhausted")

    async def fetch_weather(self, city: City) -> ValidatedBatch:
        payload = await self._get_json(
            "open_meteo_weather",
            city.city_id,
            "https://api.open-meteo.com/v1/forecast",
            {
                "latitude": city.latitude,
                "longitude": city.longitude,
                "hourly": "apparent_temperature,temperature_2m,precipitation,relative_humidity_2m,wind_speed_10m",
                "forecast_days": 7,
                "timezone": "UTC",
            },
        )
        hourly = payload["hourly"]
        validate_parallel_arrays(
            hourly,
            ["time", "apparent_temperature", "temperature_2m", "precipitation", "relative_humidity_2m", "wind_speed_10m"],
        )
        extracted_at = datetime.now(timezone.utc)
        records: list[WeatherRecord] = []
        issues = []
        for index, timestamp in enumerate(hourly["time"]):
            record_payload = {
                "city_id": city.city_id,
                "observed_at": source_utc_timestamp(timestamp),
                "apparent_temperature": hourly["apparent_temperature"][index],
                "temperature_2m": hourly["temperature_2m"][index],
                "precipitation": hourly["precipitation"][index],
                "relative_humidity": hourly["relative_humidity_2m"][index],
                "wind_speed": hourly["wind_speed_10m"][index],
                "extracted_at": extracted_at,
            }
            record, record_issues = validate_record(WeatherRecord, record_payload, timestamp)
            issues.extend(record_issues)
            if record:
                records.append(record)
        policy = self._policies["open_meteo_weather"]
        if records:
            validate_time_series(
                city.city_id, records, 1, policy.expected_interval_hours,
                allow_gaps=True,
            )
        return ValidatedBatch(records=records, issues=issues, received_records=len(hourly["time"]))

    async def fetch_air_quality(self, city: City) -> ValidatedBatch:
        payload = await self._get_json(
            "open_meteo_air_quality",
            city.city_id,
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
        validate_parallel_arrays(hourly, ["time", "pm2_5", "pm10"])
        extracted_at = datetime.now(timezone.utc)
        records: list[AirQualityRecord] = []
        issues = []
        for index, timestamp in enumerate(hourly["time"]):
            pm2_5 = hourly["pm2_5"][index]
            pm10 = hourly["pm10"][index]
            if pm2_5 is None or pm10 is None:
                issues.extend(
                    ValidationIssue(
                        natural_key=timestamp, field_name=field_name, error_type="missing_value",
                        invalid_value=None, error_message="Required pollution value is missing.",
                        record_payload={"city_id": city.city_id, "observed_at": timestamp, "pm2_5": pm2_5, "pm10": pm10},
                    )
                    for field_name, value in (("pm2_5", pm2_5), ("pm10", pm10))
                    if value is None
                )
                continue
            payload = {
                "city_id": city.city_id,
                "observed_at": source_utc_timestamp(timestamp),
                "pm2_5": pm2_5, "pm10": pm10, "extracted_at": extracted_at,
            }
            record, record_issues = validate_record(AirQualityRecord, payload, timestamp)
            issues.extend(record_issues)
            if record:
                records.append(record)
                issues.extend(cross_field_warnings("open_meteo_air_quality", record, payload, timestamp))
        policy = self._policies["open_meteo_air_quality"]
        if records:
            validate_time_series(
                city.city_id, records, 1, policy.expected_interval_hours,
                allow_gaps=True,
            )
        return ValidatedBatch(records=records, issues=issues, received_records=len(hourly["time"]))
