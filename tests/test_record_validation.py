from datetime import datetime, timezone

import pytest

import etl
from src.config import load_cities
from src.models import WeatherRecord
from src.validation import ValidatedBatch, ValidationIssue


class Metadata:
    issues = []

    def quarantine_issues(self, run_id, source, city_id, issues):
        self.issues.extend(issues)


def valid_weather() -> WeatherRecord:
    return WeatherRecord(
        city_id="delhi",
        observed_at=datetime.now(timezone.utc),
        apparent_temperature=35,
        temperature_2m=34,
        precipitation=0,
        relative_humidity=50,
        wind_speed=5,
        extracted_at=datetime.now(timezone.utc),
    )


def issue() -> ValidationIssue:
    return ValidationIssue(
        natural_key="2026-01-01T00:00:00Z",
        field_name="relative_humidity",
        error_type="less_than_equal",
        invalid_value=101,
        error_message="Input should be less than or equal to 100",
        record_payload={"relative_humidity": 101},
    )


def test_valid_records_survive_within_invalid_policy(monkeypatch) -> None:
    monkeypatch.setattr(
        etl,
        "load_extraction_policy",
        lambda: type("Policy", (), {"sources": {
            "open_meteo_weather": type("Source", (), {
                "minimum_records": 1, "minimum_valid_record_ratio": 0.5,
                "maximum_invalid_records": 2,
            })()
        }})(),
    )
    metadata = Metadata()
    records, received, rejected = etl.accepted_records(
        "run-1", "open_meteo_weather", "delhi",
        ValidatedBatch([valid_weather()], [issue()], 2), metadata,
    )
    assert len(records) == 1
    assert received == 2
    assert rejected == 1
    assert metadata.issues[0].field_name == "relative_humidity"


def test_source_city_fails_when_invalid_ratio_exceeds_policy(monkeypatch) -> None:
    monkeypatch.setattr(
        etl,
        "load_extraction_policy",
        lambda: type("Policy", (), {"sources": {
            "open_meteo_weather": type("Source", (), {
                "minimum_records": 1, "minimum_valid_record_ratio": 0.9,
                "maximum_invalid_records": 0,
            })()
        }})(),
    )
    with pytest.raises(ValueError, match="validation policy failed"):
        etl.accepted_records(
            "run-1", "open_meteo_weather", load_cities()[0].city_id,
            ValidatedBatch([valid_weather()], [issue()], 2), Metadata(),
        )
