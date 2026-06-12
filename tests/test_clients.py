from src.clients.open_meteo import OpenMeteoClient


def test_client_uses_bounded_concurrency() -> None:
    client = OpenMeteoClient(concurrency=2)
    assert client._semaphore._value == 2
