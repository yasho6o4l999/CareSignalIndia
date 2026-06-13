import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from src.config import PublicationPolicy


RunStatus = Literal["success", "partial_success", "failed"]


@dataclass(frozen=True)
class ReadinessDecision:
    status: RunStatus
    complete_cities: frozenset[str]
    incomplete_cities: frozenset[str]
    minimum_required: int

    @property
    def summary(self) -> str:
        return (
            f"complete_cities={len(self.complete_cities)}, "
            f"minimum_required={self.minimum_required}, "
            f"incomplete_cities={sorted(self.incomplete_cities)}"
        )


def evaluate_readiness(
    city_ids: set[str],
    successful_cities_by_source: dict[str, set[str]],
    policy: PublicationPolicy,
    expected_sources_by_city: dict[str, set[str]] | None = None,
    latest_source_timestamps: dict[str, dict[str, str]] | None = None,
    now: datetime | None = None,
) -> ReadinessDecision:
    expected_sources_by_city = expected_sources_by_city or {
        city_id: set(policy.required_sources) for city_id in city_ids
    }
    latest_source_timestamps = latest_source_timestamps or {}
    now = now or datetime.now(timezone.utc)

    def source_is_ready(source: str, city_id: str) -> bool:
        if city_id not in successful_cities_by_source.get(source, set()):
            return False
        latest = latest_source_timestamps.get(source, {}).get(city_id)
        if latest is None:
            return True
        latest_at = datetime.fromisoformat(latest)
        if latest_at.tzinfo is None:
            latest_at = latest_at.replace(tzinfo=timezone.utc)
        return (now - latest_at).total_seconds() <= policy.sources[source].maximum_age_hours * 3600

    complete = {
        city_id
        for city_id in city_ids
        if all(
            source_is_ready(source, city_id)
            for source in expected_sources_by_city.get(city_id, set(policy.required_sources))
            if source in policy.required_sources
        )
    }

    minimum_required = max(
        policy.minimum_complete_cities,
        math.ceil(len(city_ids) * policy.minimum_complete_city_ratio),
    )
    if len(complete) == len(city_ids):
        status: RunStatus = "success"
    elif len(complete) >= minimum_required and set(policy.mandatory_cities) <= complete:
        status = "partial_success"
    else:
        status = "failed"
    return ReadinessDecision(
        status=status,
        complete_cities=frozenset(complete),
        incomplete_cities=frozenset(city_ids - complete),
        minimum_required=minimum_required,
    )
