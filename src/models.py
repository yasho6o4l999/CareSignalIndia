from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class WeatherRecord(BaseModel):
    city_id: str
    observed_at: datetime
    apparent_temperature: float = Field(ge=-80, le=80)
    precipitation: float = Field(ge=0, le=1000)
    relative_humidity: float = Field(ge=0, le=100)
    wind_speed: float = Field(ge=0, le=500)
    source: Literal["open_meteo_weather"] = "open_meteo_weather"
    extracted_at: datetime

    @field_validator("observed_at", "extracted_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(timezone.utc)


class AirQualityRecord(BaseModel):
    city_id: str
    observed_at: datetime
    pm2_5: float = Field(ge=0, le=2000)
    pm10: float = Field(ge=0, le=3000)
    source: Literal["open_meteo_air_quality"] = "open_meteo_air_quality"
    extracted_at: datetime

    @field_validator("observed_at", "extracted_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(timezone.utc)


class QualityResult(BaseModel):
    run_id: str
    check_name: str
    dataset: str
    status: Literal["pass", "warning", "fail"]
    details: str
    checked_at: datetime

