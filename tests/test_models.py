from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.models import AirQualityRecord, WeatherRecord


def test_weather_rejects_invalid_humidity() -> None:
    with pytest.raises(ValidationError):
        WeatherRecord(
            city_id="delhi",
            observed_at=datetime.now(timezone.utc),
            apparent_temperature=40,
            temperature_2m=39,
            precipitation=0,
            relative_humidity=101,
            wind_speed=5,
            extracted_at=datetime.now(timezone.utc),
        )


def test_air_quality_rejects_negative_pollution() -> None:
    with pytest.raises(ValidationError):
        AirQualityRecord(
            city_id="delhi",
            observed_at=datetime.now(timezone.utc),
            pm2_5=-1,
            pm10=10,
            extracted_at=datetime.now(timezone.utc),
        )
