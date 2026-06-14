import httpx
import pytest
from datetime import datetime, timedelta, timezone

from src.clients.open_meteo import OpenMeteoClient
from src.config import load_cities
from src.validation import source_utc_timestamp


def test_client_uses_bounded_concurrency() -> None:
    client = OpenMeteoClient(concurrency=2)
    assert client._semaphore._value == 2
    assert client._semaphores["open_meteo_weather"]._value == 2


def test_source_timestamp_normalization_accepts_naive_and_offset_values() -> None:
    assert source_utc_timestamp("2026-06-14T10:00").isoformat() == "2026-06-14T10:00:00+00:00"
    assert source_utc_timestamp("2026-06-14T15:30+05:30").isoformat() == "2026-06-14T10:00:00+00:00"
    assert source_utc_timestamp("not-a-timestamp") == "not-a-timestamp"


@pytest.mark.asyncio
async def test_client_does_not_retry_non_transient_http_errors() -> None:
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(400, request=request)

    client = OpenMeteoClient(attempts=4)
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        await client.fetch_weather(load_cities()[0])
    await client._client.aclose()

    assert attempts == 1
    assert client.metrics[0]["attempts"] == 1


@pytest.mark.asyncio
async def test_client_does_not_retry_invalid_json() -> None:
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, text="not-json", request=request)

    client = OpenMeteoClient(attempts=4)
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError):
        await client.fetch_weather(load_cities()[0])
    await client._client.aclose()

    assert attempts == 1
    assert client.metrics[0]["status"] == "invalid_json"


@pytest.mark.asyncio
async def test_client_salvages_valid_weather_records() -> None:
    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    times = [(start + timedelta(hours=index)).replace(tzinfo=None).isoformat() for index in range(25)]
    humidity = [50] * 25
    humidity[4] = 101
    payload = {
        "hourly": {
            "time": times,
            "apparent_temperature": [35] * 25,
            "temperature_2m": [34] * 25,
            "precipitation": [0] * 25,
            "relative_humidity_2m": humidity,
            "wind_speed_10m": [5] * 25,
        }
    }

    client = OpenMeteoClient()
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload, request=request))
    )
    batch = await client.fetch_weather(load_cities()[0])
    await client._client.aclose()

    assert len(batch.records) == 24
    assert batch.invalid_records == 1
    assert batch.issues[0].field_name == "relative_humidity"


@pytest.mark.asyncio
async def test_client_returns_evidence_when_all_weather_records_are_invalid() -> None:
    payload = {
        "hourly": {
            "time": ["not-a-timestamp"],
            "apparent_temperature": [35],
            "temperature_2m": [34],
            "precipitation": [0],
            "relative_humidity_2m": [101],
            "wind_speed_10m": [5],
        }
    }
    client = OpenMeteoClient()
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload, request=request))
    )
    batch = await client.fetch_weather(load_cities()[0])
    await client._client.aclose()

    assert batch.records == []
    assert batch.received_records == 1
    assert batch.invalid_records == 1
    assert {issue.field_name for issue in batch.issues} == {"observed_at", "relative_humidity"}
