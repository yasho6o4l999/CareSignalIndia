import math
from dataclasses import dataclass
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
) -> ReadinessDecision:
    complete = set(city_ids)
    for source in policy.required_sources:
        complete &= successful_cities_by_source.get(source, set())

    minimum_required = max(
        policy.minimum_complete_cities,
        math.ceil(len(city_ids) * policy.minimum_complete_city_ratio),
    )
    if len(complete) == len(city_ids):
        status: RunStatus = "success"
    elif len(complete) >= minimum_required:
        status = "partial_success"
    else:
        status = "failed"
    return ReadinessDecision(
        status=status,
        complete_cities=frozenset(complete),
        incomplete_cities=frozenset(city_ids - complete),
        minimum_required=minimum_required,
    )
