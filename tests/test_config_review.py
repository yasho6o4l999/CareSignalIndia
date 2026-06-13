from src.config import CONFIG_ROOT, Rule
from src.config_review import (
    ConfigurationSnapshot,
    compare_snapshots,
    detect_rule_conflicts,
    load_snapshot,
)


PROFILES = {"all_chronic": {"diabetes": "high", "respiratory": "high"}}


def rule(rule_id: str, predicates: list[dict], cities: list[str] | None = None) -> Rule:
    return Rule(
        rule_id=rule_id,
        predicates=predicates,
        persistence_hours=3,
        severity="high",
        cities=cities or ["delhi"],
        months=[1],
    )


def test_detects_duplicate_and_impossible_rules() -> None:
    predicate = [{"metric": "temperature_2m", "operator": "greater_than_or_equal", "threshold": 40}]
    impossible = rule(
        "impossible",
        [
            {"metric": "temperature_2m", "operator": "greater_than_or_equal", "threshold": 40},
            {"metric": "temperature_2m", "operator": "less_than_or_equal", "threshold": 30},
        ],
    )

    findings = detect_rule_conflicts(
        [rule("first", predicate), rule("duplicate", predicate), impossible],
        PROFILES,
    )

    assert {finding.kind for finding in findings if finding.level == "error"} == {
        "duplicate_signal_scope",
        "impossible_predicate_range",
    }


def test_detects_nested_overlap_as_warning() -> None:
    broad = rule(
        "broad",
        [{"metric": "pm2_5", "operator": "greater_than_or_equal", "threshold": 60}],
    )
    compound = rule(
        "compound",
        [
            {"metric": "pm2_5", "operator": "greater_than_or_equal", "threshold": 60},
            {"metric": "temperature_2m", "operator": "less_than_or_equal", "threshold": 10},
        ],
    )

    findings = detect_rule_conflicts([broad, compound], PROFILES)

    assert len(findings) == 1
    assert findings[0].level == "warning"
    assert findings[0].kind == "nested_signal_overlap"


def test_detects_different_thresholds_on_same_signal_dimension() -> None:
    findings = detect_rule_conflicts(
        [
            rule(
                "broad_heat",
                [{"metric": "temperature_2m", "operator": "greater_than_or_equal", "threshold": 35}],
            ),
            rule(
                "severe_heat",
                [{"metric": "temperature_2m", "operator": "greater_than_or_equal", "threshold": 40}],
            ),
        ],
        PROFILES,
    )

    assert len(findings) == 1
    assert findings[0].kind == "threshold_signal_overlap"


def test_impact_report_quantifies_rule_scope_and_member_exposure() -> None:
    snapshot = load_snapshot(CONFIG_ROOT)
    heat = next(item for item in snapshot.rules if item.rule_id == "heat_stress")
    changed_heat = heat.model_copy(update={"cities": [*heat.cities, "new-city"]})
    candidate = ConfigurationSnapshot(
        rules=tuple(changed_heat if item.rule_id == "heat_stress" else item for item in snapshot.rules),
        condition_profiles=snapshot.condition_profiles,
        publication_policy=snapshot.publication_policy,
        runtime_settings=snapshot.runtime_settings,
        city_ids=(*snapshot.city_ids, "new-city"),
    )

    report = compare_snapshots(snapshot, candidate)

    assert report.changed_rules == ("heat_stress",)
    assert report.added_cities == ("new-city",)
    assert report.city_month_scopes_added == 12
    assert report.condition_links_added == 48
    assert "new-city" in report.affected_cities
