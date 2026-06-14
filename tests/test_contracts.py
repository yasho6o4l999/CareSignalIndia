from datetime import datetime, timedelta, timezone

import pytest

from src.contracts import validate_parallel_arrays, validate_time_series
from src.models import WeatherRecord


def record(observed_at: datetime) -> WeatherRecord:
    return WeatherRecord(
        city_id="delhi",
        observed_at=observed_at,
        apparent_temperature=31,
        temperature_2m=30,
        precipitation=0,
        relative_humidity=50,
        wind_speed=5,
        extracted_at=observed_at,
    )


def test_response_contract_rejects_misaligned_arrays() -> None:
    with pytest.raises(ValueError, match="different lengths"):
        validate_parallel_arrays({"time": [1, 2], "temperature": [1]}, ["time", "temperature"])


def test_time_series_contract_rejects_duplicate_and_missing_intervals() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="duplicate"):
        validate_time_series("delhi", [record(start), record(start)], 2, 1)
    with pytest.raises(ValueError, match="unexpected intervals"):
        validate_time_series("delhi", [record(start), record(start + timedelta(hours=2))], 2, 1)
