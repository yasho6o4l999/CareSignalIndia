import pytest
from pydantic import ValidationError

from src.config import Rule, load_cities, load_rules


def test_configuration_is_valid() -> None:
    assert len(load_cities()) == 5
    assert any(rule.rule_id == "delhi_winter_pm25" for rule in load_rules())


def test_rule_rejects_invalid_month() -> None:
    with pytest.raises(ValidationError):
        Rule(
            rule_id="invalid",
            metric="pm2_5",
            operator="greater_than_or_equal",
            threshold=60,
            persistence_hours=1,
            severity="high",
            relevant_conditions=["respiratory"],
            cities=["delhi"],
            months=[13],
        )

