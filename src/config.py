import hashlib
import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = ROOT / "config"
Condition = Literal["diabetes", "cardiovascular", "renal", "respiratory"]
ClimateZone = Literal[
    "north_inland",
    "northwest_inland",
    "west_inland",
    "west_coastal",
    "south_coastal",
    "south_plateau",
]
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
    "pm2_5_rolling_24h",
]
SourceName = Literal["open_meteo_weather", "open_meteo_air_quality", "nasa_power_daily"]
Severity = Literal["low", "medium", "high", "critical"]
SignalCategory = Literal["environmental_health_risk", "care_access_disruption"]
RuleStatus = Literal["prototype", "approved", "retired"]
Relevance = Literal["low", "medium", "high"]


def _unique(values: list[Any], field_name: str) -> list[Any]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must contain unique values")
    return values


class City(BaseModel):
    city_id: str
    city_name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone: str
    climate_zone: ClimateZone
    enabled: bool = True
    criticality: Literal["standard", "high"] = "standard"
    population_weight: float = Field(default=1.0, gt=0)
    supported_languages: list[str] = Field(min_length=1)
    expected_sources: list[SourceName] = Field(min_length=1)

    @field_validator("supported_languages", "expected_sources")
    @classmethod
    def unique_lists(cls, value: list[Any], info) -> list[Any]:
        return _unique(value, info.field_name)


class SourcePolicy(BaseModel):
    maximum_age_hours: int = Field(ge=1)
    required: bool = True


class PublicationPolicy(BaseModel):
    sources: dict[SourceName, SourcePolicy]
    minimum_complete_cities: int = Field(ge=1)
    minimum_complete_city_ratio: float = Field(gt=0, le=1)
    mandatory_cities: list[str] = Field(default_factory=list)

    @field_validator("mandatory_cities")
    @classmethod
    def unique_mandatory_cities(cls, value: list[str]) -> list[str]:
        return _unique(value, "mandatory_cities")

    @property
    def required_sources(self) -> list[SourceName]:
        return [source for source, policy in self.sources.items() if policy.required]


class IncrementalPolicy(BaseModel):
    forecast_correction_lookback_hours: int = Field(ge=0, le=168)


class OutreachPolicy(BaseModel):
    cooldown_hours: int = Field(ge=0, le=720)
    repeat_when_severity_increases: bool = True


class SyntheticMemberPolicy(BaseModel):
    member_count: int = Field(ge=1)
    seed: int
    anchor_date: date
    city_weights: dict[str, float] = Field(default_factory=dict)


class RuntimeSettings(BaseModel):
    enabled_cities: list[str] | None = None
    synthetic_members: SyntheticMemberPolicy


class SourceReference(BaseModel):
    name: str
    url: str


class Aggregation(BaseModel):
    function: Literal["instantaneous", "rolling_average", "daily_sum", "daily_min", "daily_max", "daily_range"]
    window_hours: int | None = Field(default=None, ge=1, le=168)

    @model_validator(mode="after")
    def window_required_for_rolling(self) -> "Aggregation":
        if self.function == "rolling_average" and self.window_hours is None:
            raise ValueError("rolling_average requires window_hours")
        if self.function != "rolling_average" and self.window_hours is not None:
            raise ValueError("window_hours is only supported for rolling_average")
        return self


class RulePredicate(BaseModel):
    metric: Metric
    operator: Literal["greater_than_or_equal", "less_than_or_equal"]
    comparison: Literal["absolute", "baseline_percentile"] = "absolute"
    threshold: float | None = None
    baseline_percentile: Literal["p10", "p90", "p95"] | None = None
    aggregation: Aggregation = Aggregation(function="instantaneous")

    @model_validator(mode="after")
    def valid_comparison_configuration(self) -> "RulePredicate":
        if self.comparison == "absolute" and self.threshold is None:
            raise ValueError("absolute predicates require threshold")
        if self.comparison == "baseline_percentile" and self.baseline_percentile is None:
            raise ValueError("baseline predicates require baseline_percentile")
        if self.comparison == "baseline_percentile" and self.threshold is not None:
            raise ValueError("baseline predicates must not define a fixed threshold")
        if self.metric == "pm2_5_rolling_24h" and (
            self.aggregation.function != "rolling_average" or self.aggregation.window_hours != 24
        ):
            raise ValueError("pm2_5_rolling_24h requires a 24-hour rolling_average")
        return self


class SeverityBand(BaseModel):
    severity: Severity
    minimum_persistence_hours: int = Field(ge=1, le=168)
    minimum_threshold_ratio: float = Field(default=1.0, ge=1)


class Rule(BaseModel):
    rule_id: str
    name: str = ""
    description: str = ""
    category: SignalCategory = "environmental_health_risk"
    owner: str = "care_operations"
    status: RuleStatus = "prototype"
    rationale: str = "Prototype environmental signal requiring domain review."
    source_references: list[SourceReference] = Field(
        default_factory=lambda: [
            SourceReference(name="Prototype source catalog", url="https://open-meteo.com/en/docs")
        ]
    )
    predicates: list[RulePredicate] = Field(min_length=1)
    condition_logic: Literal["all"] = "all"
    persistence_hours: int = Field(ge=1, le=168)
    severity: Severity
    severity_bands: list[SeverityBand] = Field(default_factory=list)
    condition_profile: str = "all_chronic"
    relevant_conditions: list[Condition] | None = None
    cities: list[str] = Field(min_length=1)
    months: list[int] = Field(min_length=1)

    @field_validator("cities", "months")
    @classmethod
    def unique_dimensions(cls, value: list[Any], info) -> list[Any]:
        return _unique(value, info.field_name)

    @field_validator("relevant_conditions")
    @classmethod
    def unique_conditions(cls, value: list[Condition] | None) -> list[Condition] | None:
        return _unique(value, "relevant_conditions") if value else value

    @field_validator("months")
    @classmethod
    def valid_months(cls, value: list[int]) -> list[int]:
        if any(month < 1 or month > 12 for month in value):
            raise ValueError("months must contain values from 1 through 12")
        return value

    @model_validator(mode="after")
    def valid_rule_semantics(self) -> "Rule":
        predicate_keys = [
            json.dumps(predicate.model_dump(mode="json"), sort_keys=True)
            for predicate in self.predicates
        ]
        _unique(predicate_keys, "predicates")
        if self.severity_bands:
            band_keys = [
                (band.minimum_persistence_hours, band.minimum_threshold_ratio)
                for band in self.severity_bands
            ]
            _unique(band_keys, "severity_bands")
            severity_rank = {"low": 1, "medium": 2, "high": 3, "critical": 4}
            for left in self.severity_bands:
                for right in self.severity_bands:
                    right_is_stronger = (
                        right.minimum_persistence_hours >= left.minimum_persistence_hours
                        and right.minimum_threshold_ratio >= left.minimum_threshold_ratio
                    )
                    if right_is_stronger and severity_rank[right.severity] < severity_rank[left.severity]:
                        raise ValueError(
                            "severity must not decrease as persistence and threshold ratio increase"
                        )
        return self


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_runtime_settings(environment: str | None = None) -> RuntimeSettings:
    environment = environment or os.getenv("CARESIGNAL_ENV", "development")
    base = _load_yaml(CONFIG_ROOT / "runtime.yml")
    override_path = CONFIG_ROOT / "environments" / f"{environment}.yml"
    override = _load_yaml(override_path) if override_path.exists() else {}
    settings = RuntimeSettings.model_validate(_deep_merge(base, override))
    city_ids = {item["city_id"] for item in _load_yaml(CONFIG_ROOT / "cities.yml")["cities"]}
    unknown_enabled = set(settings.enabled_cities or []) - city_ids
    unknown_weights = set(settings.synthetic_members.city_weights) - city_ids
    if unknown_enabled:
        raise ValueError(f"enabled_cities reference unknown cities: {sorted(unknown_enabled)}")
    if unknown_weights:
        raise ValueError(f"city_weights reference unknown cities: {sorted(unknown_weights)}")
    return settings


def load_cities(environment: str | None = None) -> list[City]:
    cities = [City.model_validate(item) for item in _load_yaml(CONFIG_ROOT / "cities.yml")["cities"]]
    city_ids = [city.city_id for city in cities]
    _unique(city_ids, "city IDs")
    enabled = load_runtime_settings(environment).enabled_cities
    return [city for city in cities if city.enabled and (enabled is None or city.city_id in enabled)]


def load_condition_profiles() -> dict[str, dict[Condition, Relevance]]:
    profiles = _load_yaml(CONFIG_ROOT / "condition_relevance.yml")["profiles"]
    return {
        profile_id: {condition: relevance for condition, relevance in profile.items()}
        for profile_id, profile in profiles.items()
    }


def load_publication_policy() -> PublicationPolicy:
    policy = PublicationPolicy.model_validate(_load_yaml(CONFIG_ROOT / "publication_policy.yml"))
    city_ids = {city.city_id for city in load_cities()}
    if policy.minimum_complete_cities > len(city_ids):
        raise ValueError("minimum_complete_cities cannot exceed configured cities")
    unknown = set(policy.mandatory_cities) - city_ids
    if unknown:
        raise ValueError(f"mandatory_cities reference unknown or disabled cities: {sorted(unknown)}")
    return policy


def load_incremental_policy() -> IncrementalPolicy:
    return IncrementalPolicy.model_validate(_load_yaml(CONFIG_ROOT / "incremental_policy.yml"))


def load_outreach_policy() -> OutreachPolicy:
    return OutreachPolicy.model_validate(_load_yaml(CONFIG_ROOT / "outreach_policy.yml"))


def load_rules() -> list[Rule]:
    items = _load_yaml(CONFIG_ROOT / "regional_rules.yml")["rules"]
    metadata = _load_yaml(CONFIG_ROOT / "signal_catalog.yml")["signals"]
    rule_ids = {item["rule_id"] for item in items}
    if set(metadata) != rule_ids:
        raise ValueError(
            "signal_catalog.yml and regional_rules.yml must contain exactly the same rule IDs"
        )
    items = [_deep_merge(item, metadata.get(item["rule_id"], {})) for item in items]
    rules = [Rule.model_validate(item) for item in items]
    _unique([rule.rule_id for rule in rules], "rule IDs")
    city_ids = {city.city_id for city in load_cities()}
    profiles = load_condition_profiles()
    unknown_cities = {city for rule in rules for city in rule.cities if city not in city_ids}
    unknown_profiles = {rule.condition_profile for rule in rules if rule.condition_profile not in profiles}
    if unknown_cities:
        raise ValueError(f"Rules reference unknown or disabled cities: {sorted(unknown_cities)}")
    if unknown_profiles:
        raise ValueError(f"Rules reference unknown condition profiles: {sorted(unknown_profiles)}")
    return [rule for rule in rules if rule.status != "retired"]


def configuration_version() -> str:
    payload = {
        "cities": [city.model_dump(mode="json") for city in load_cities()],
        "rules": [rule.model_dump(mode="json") for rule in load_rules()],
        "condition_profiles": load_condition_profiles(),
        "publication": load_publication_policy().model_dump(mode="json"),
        "incremental": load_incremental_policy().model_dump(mode="json"),
        "outreach": load_outreach_policy().model_dump(mode="json"),
        "runtime": load_runtime_settings().model_dump(mode="json"),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
