import httpx
import pytest

from src.clients.open_meteo import OpenMeteoClient
from src.config import load_cities


def test_client_uses_bounded_concurrency() -> None:
    client = OpenMeteoClient(concurrency=2)
    assert client._semaphore._value == 2
    assert client._semaphores["open_meteo_weather"]._value == 2


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
