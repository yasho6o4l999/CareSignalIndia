from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator


ROOT = Path(__file__).resolve().parents[1]


class City(BaseModel):
    city_id: str
    city_name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone: str
    climate_zone: str


class Rule(BaseModel):
    rule_id: str
    metric: Literal["apparent_temperature", "precipitation", "pm2_5"]
    operator: Literal["greater_than_or_equal", "less_than_or_equal"]
    threshold: float
    persistence_hours: int = Field(ge=1, le=168)
    severity: Literal["low", "medium", "high"]
    relevant_conditions: list[str] = Field(min_length=1)
    cities: list[str] = Field(min_length=1)
    months: list[int] = Field(min_length=1)

    @field_validator("months")
    @classmethod
    def valid_months(cls, value: list[int]) -> list[int]:
        if not value or any(month < 1 or month > 12 for month in value):
            raise ValueError("months must contain values from 1 through 12")
        return value


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_cities() -> list[City]:
    return [City.model_validate(item) for item in _load_yaml(ROOT / "config/cities.yml")["cities"]]


def load_rules() -> list[Rule]:
    rules = [Rule.model_validate(item) for item in _load_yaml(ROOT / "config/regional_rules.yml")["rules"]]
    rule_ids = [rule.rule_id for rule in rules]
    if len(rule_ids) != len(set(rule_ids)):
        raise ValueError("Rule IDs must be unique")
    city_ids = {city.city_id for city in load_cities()}
    unknown = {city for rule in rules for city in rule.cities if city not in city_ids}
    if unknown:
        raise ValueError(f"Rules reference unknown cities: {sorted(unknown)}")
    return rules
