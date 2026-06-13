import pytest
from pydantic import ValidationError

from src.config import (
    Rule,
    configuration_version,
    load_cities,
    load_incremental_policy,
    load_outreach_policy,
    load_publication_policy,
    load_rules,
)


def test_configuration_is_valid() -> None:
    assert len(load_cities()) == 7
    assert any(rule.rule_id == "delhi_winter_pm25" for rule in load_rules())
    assert load_publication_policy().minimum_complete_cities == 5
    assert load_incremental_policy().forecast_correction_lookback_hours == 24
    assert load_outreach_policy().cooldown_hours == 24
    assert configuration_version() == configuration_version()


def test_rule_rejects_invalid_month() -> None:
    with pytest.raises(ValidationError):
        Rule(
            rule_id="invalid",
            predicates=[{"metric": "pm2_5", "operator": "greater_than_or_equal", "threshold": 60}],
            persistence_hours=1,
            severity="high",
            relevant_conditions=["respiratory"],
            cities=["delhi"],
            months=[13],
        )


def test_rule_rejects_empty_city_list() -> None:
    with pytest.raises(ValidationError):
        Rule(
            rule_id="invalid",
            predicates=[{"metric": "pm2_5", "operator": "greater_than_or_equal", "threshold": 60}],
            persistence_hours=1,
            severity="high",
            relevant_conditions=["respiratory"],
            cities=[],
            months=[1],
        )


def test_baseline_rule_requires_percentile_without_fixed_threshold() -> None:
    with pytest.raises(ValidationError):
        Rule(
            rule_id="invalid_baseline",
            predicates=[{
                "metric": "temperature_2m",
                "operator": "greater_than_or_equal",
                "comparison": "baseline_percentile",
            }],
            persistence_hours=3,
            severity="medium",
            relevant_conditions=["cardiovascular"],
            cities=["delhi"],
            months=[6],
        )
