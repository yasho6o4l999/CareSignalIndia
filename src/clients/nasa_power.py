import asyncio
import random
import time
from datetime import date, datetime, timezone

import httpx

from src.config import City, ExtractionSourcePolicy, load_extraction_policy
from src.contracts import validate_time_series
from src.models import HistoricalWeatherRecord
from src.validation import ValidatedBatch, ValidationIssue, validate_record


TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
MISSING_VALUE = -999.0


class NasaPowerClient:
    def __init__(self, concurrency: int | None = None, attempts: int | None = None) -> None:
        policy = load_extraction_policy().sources["nasa_power_daily"]
        concurrency = concurrency or policy.maximum_concurrency
        self._policy = policy
        self._semaphore = asyncio.Semaphore(concurrency)
        self._attempts = attempts or policy.maximum_attempts
        self.metrics: list[dict] = []
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(policy.timeout_seconds),
            limits=httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency),
            headers={"User-Agent": "CareSignal-India-Candidate-Assignment/0.1"},
        )

    async def __aenter__(self) -> "NasaPowerClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.aclose()

    async def _get_json(self, city_id: str, params: dict) -> dict:
        started = time.perf_counter()
        status_code = None
        response_bytes = 0
        async with self._semaphore:
            for attempt in range(1, self._attempts + 1):
                try:
                    response = await self._client.get(
                        "https://power.larc.nasa.gov/api/temporal/daily/point",
                        params=params,
                    )
                    status_code = response.status_code
                    response_bytes = len(response.content)
                    if response.status_code in TRANSIENT_STATUS_CODES:
                        raise httpx.HTTPStatusError("transient response", request=response.request, response=response)
                    response.raise_for_status()
                    payload = response.json()
                    self.metrics.append({"source": "nasa_power_daily", "city_id": city_id, "duration_ms": round((time.perf_counter() - started) * 1000), "attempts": attempt, "http_status": status_code, "response_bytes": response_bytes, "status": "success"})
                    return payload
                except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as error:
                    retryable = not isinstance(error, httpx.HTTPStatusError) or (
                        error.response.status_code in TRANSIENT_STATUS_CODES
                    )
                    if attempt == self._attempts or not retryable:
                        self.metrics.append({"source": "nasa_power_daily", "city_id": city_id, "duration_ms": round((time.perf_counter() - started) * 1000), "attempts": attempt, "http_status": status_code, "response_bytes": response_bytes, "status": "failed"})
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
                            "source": "nasa_power_daily", "city_id": city_id,
                            "duration_ms": round((time.perf_counter() - started) * 1000),
                            "attempts": attempt, "http_status": status_code,
                            "response_bytes": response_bytes, "status": "invalid_json",
                        }
                    )
                    raise
        raise RuntimeError("request attempts exhausted")

    async def fetch_daily_history(self, city: City, start: date, end: date) -> ValidatedBatch:
        payload = await self._get_json(
            city.city_id,
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
        issues = []
        for date_key, temperature_value in temperature.items():
            precipitation_value = precipitation.get(date_key)
            minimum_temperature_value = minimum_temperature.get(date_key)
            if (
                temperature_value == MISSING_VALUE
                or minimum_temperature_value in (None, MISSING_VALUE)
                or precipitation_value in (None, MISSING_VALUE)
            ):
                issues.append(
                    ValidationIssue(
                        natural_key=date_key,
                        field_name="historical_measurements",
                        error_type="missing_source_value",
                        invalid_value=MISSING_VALUE,
                        error_message="NASA POWER missing-value sentinel or null encountered.",
                        record_payload={
                            "city_id": city.city_id,
                            "observed_date": date_key,
                            "temperature_2m": temperature_value,
                            "minimum_temperature_2m": minimum_temperature_value,
                            "precipitation": precipitation_value,
                        },
                    )
                )
                continue
            try:
                observed_date = datetime.strptime(date_key, "%Y%m%d").replace(tzinfo=timezone.utc)
            except ValueError as error:
                issues.append(
                    ValidationIssue(
                        natural_key=date_key,
                        field_name="observed_date",
                        error_type="invalid_date_key",
                        invalid_value=date_key,
                        error_message=str(error),
                        record_payload={"city_id": city.city_id, "observed_date": date_key},
                    )
                )
                continue
            record, record_issues = validate_record(
                HistoricalWeatherRecord,
                {
                    "city_id": city.city_id,
                    "observed_date": observed_date,
                    "temperature_2m": temperature_value,
                    "minimum_temperature_2m": minimum_temperature_value,
                    "temperature_range": temperature_value - minimum_temperature_value,
                    "precipitation": precipitation_value,
                    "extracted_at": extracted_at,
                },
                date_key,
            )
            issues.extend(record_issues)
            if record:
                records.append(record)
        if records:
            validate_time_series(
                city.city_id, records, 1, self._policy.expected_interval_hours,
                allow_gaps=True,
            )
        return ValidatedBatch(records=records, issues=issues, received_records=len(temperature))
