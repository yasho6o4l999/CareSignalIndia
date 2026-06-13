from src.config import load_rules
from src.rules import compile_rules


def test_compile_rules_expands_city_month_and_condition_dimensions() -> None:
    definitions, predicates, conditions = compile_rules(load_rules())
    delhi_winter = [row for row in definitions if row["rule_id"] == "delhi_winter_pm25"]

    assert len(delhi_winter) == 4
    assert {row["month"] for row in delhi_winter} == {1, 10, 11, 12}
    assert {row["city_id"] for row in delhi_winter} == {"delhi"}
    assert {
        row["condition"] for row in conditions if row["rule_id"] == "delhi_winter_pm25"
    } == {"respiratory", "cardiovascular"}


def test_ruleset_version_is_deterministic() -> None:
    first, _, _ = compile_rules(load_rules())
    second, _, _ = compile_rules(load_rules())
    assert first[0]["ruleset_version"] == second[0]["ruleset_version"]


def test_compiled_baseline_rule_keeps_comparison_metadata() -> None:
    _, predicates, _ = compile_rules(load_rules())
    baseline_rule = next(row for row in predicates if row["rule_id"] == "locally_unusual_heat")
    assert baseline_rule["comparison"] == "baseline_percentile"
    assert baseline_rule["baseline_percentile"] == "p95"
    assert baseline_rule["threshold"] is None


def test_special_scenarios_are_configured_as_compound_and_regional_rules() -> None:
    rules = {rule.rule_id: rule for rule in load_rules()}
    expected = {
        "mumbai_monsoon_disruption",
        "chennai_northeast_monsoon_disruption",
        "coastal_heat_humidity_stress",
        "ahmedabad_sustained_hot_nights",
        "coastal_high_wind_disruption",
        "winter_cold_pollution_compound",
        "jaipur_temperature_swing",
    }
    assert expected <= rules.keys()
    assert len(rules["chennai_northeast_monsoon_disruption"].predicates) == 2
    assert len(rules["coastal_heat_humidity_stress"].predicates) == 2
    assert len(rules["winter_cold_pollution_compound"].predicates) == 2
