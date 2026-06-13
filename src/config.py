from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


ROOT = Path(__file__).resolve().parents[1]
Metric = Literal[
    "apparent_temperature",
    "temperature_2m",
    "precipitation",
    "daily_precipitation_sum",
    "daily_min_temperature",
    "daily_max_temperature",
    "daily_temperature_range",
    "apparent_temperature_uplift",
    "relative_humidity",
    "wind_speed",
    "pm2_5",
]
SourceName = Literal["open_meteo_weather", "open_meteo_air_quality", "nasa_power_daily"]


class City(BaseModel):
    city_id: str
    city_name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone: str
    climate_zone: str


class PublicationPolicy(BaseModel):
    required_sources: list[SourceName] = Field(min_length=1)
    minimum_complete_cities: int = Field(ge=1)
    minimum_complete_city_ratio: float = Field(gt=0, le=1)

    @field_validator("required_sources")
    @classmethod
    def unique_required_sources(cls, value: list[SourceName]) -> list[SourceName]:
        if len(value) != len(set(value)):
            raise ValueError("required_sources must be unique")
        return value


class IncrementalPolicy(BaseModel):
    forecast_correction_lookback_hours: int = Field(ge=0, le=168)


class RulePredicate(BaseModel):
    metric: Metric
    operator: Literal["greater_than_or_equal", "less_than_or_equal"]
    comparison: Literal["absolute", "baseline_percentile"] = "absolute"
    threshold: float | None = None
    baseline_percentile: Literal["p10", "p90", "p95"] | None = None

    @model_validator(mode="after")
    def valid_comparison_configuration(self) -> "RulePredicate":
        if self.comparison == "absolute" and self.threshold is None:
            raise ValueError("absolute predicates require threshold")
        if self.comparison == "baseline_percentile" and self.baseline_percentile is None:
            raise ValueError("baseline predicates require baseline_percentile")
        if self.comparison == "baseline_percentile" and self.threshold is not None:
            raise ValueError("baseline predicates must not define a fixed threshold")
        return self


class Rule(BaseModel):
    rule_id: str
    predicates: list[RulePredicate] = Field(min_length=1)
    condition_logic: Literal["all"] = "all"
    persistence_hours: int = Field(ge=1, le=168)
    severity: Literal["low", "medium", "high"]
    relevant_conditions: list[str] = Field(min_length=1)
    cities: list[str] = Field(min_length=1)
    months: list[int] = Field(min_length=1)

    @field_validator("months")
    @classmethod
    def valid_months(cls, value: list[int]) -> list[int]:
        if any(month < 1 or month > 12 for month in value):
            raise ValueError("months must contain values from 1 through 12")
        return value


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_cities() -> list[City]:
    return [City.model_validate(item) for item in _load_yaml(ROOT / "config/cities.yml")["cities"]]


def load_publication_policy() -> PublicationPolicy:
    policy = PublicationPolicy.model_validate(_load_yaml(ROOT / "config/publication_policy.yml"))
    if policy.minimum_complete_cities > len(load_cities()):
        raise ValueError("minimum_complete_cities cannot exceed configured cities")
    return policy


def load_incremental_policy() -> IncrementalPolicy:
    return IncrementalPolicy.model_validate(_load_yaml(ROOT / "config/incremental_policy.yml"))


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
