from src.config import load_rules
from src.rules import compile_rules


def test_compile_rules_expands_city_month_and_condition_dimensions() -> None:
    definitions, conditions = compile_rules(load_rules())
    delhi_winter = [row for row in definitions if row["rule_id"] == "delhi_winter_pm25"]

    assert len(delhi_winter) == 4
    assert {row["month"] for row in delhi_winter} == {1, 10, 11, 12}
    assert {row["city_id"] for row in delhi_winter} == {"delhi"}
    assert {
        row["condition"] for row in conditions if row["rule_id"] == "delhi_winter_pm25"
    } == {"respiratory", "cardiovascular"}


def test_ruleset_version_is_deterministic() -> None:
    first, _ = compile_rules(load_rules())
    second, _ = compile_rules(load_rules())
    assert first[0]["ruleset_version"] == second[0]["ruleset_version"]
