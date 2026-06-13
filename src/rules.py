import hashlib
import json

from src.config import Rule


OPERATOR_LABELS = {
    "greater_than_or_equal": "at or above",
    "less_than_or_equal": "at or below",
}


def compile_rules(rules: list[Rule]) -> tuple[list[dict], list[dict], list[dict]]:
    canonical = json.dumps(
        [rule.model_dump(mode="json") for rule in rules],
        sort_keys=True,
        separators=(",", ":"),
    )
    ruleset_version = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    definitions: list[dict] = []
    predicates: list[dict] = []
    cohort_conditions: list[dict] = []

    for rule in rules:
        for city_id in rule.cities:
            for month in rule.months:
                definitions.append(
                    {
                        "ruleset_version": ruleset_version,
                        "rule_id": rule.rule_id,
                        "city_id": city_id,
                        "month": month,
                        "condition_logic": rule.condition_logic,
                        "predicate_count": len(rule.predicates),
                        "persistence_hours": rule.persistence_hours,
                        "severity": rule.severity,
                    }
                )
        for predicate_index, predicate in enumerate(rule.predicates, start=1):
            predicates.append(
                {
                    "ruleset_version": ruleset_version,
                    "rule_id": rule.rule_id,
                    "predicate_index": predicate_index,
                    "metric": predicate.metric,
                    "operator": predicate.operator,
                    "operator_label": OPERATOR_LABELS[predicate.operator],
                    "comparison": predicate.comparison,
                    "threshold": predicate.threshold,
                    "baseline_percentile": predicate.baseline_percentile,
                }
            )
        cohort_conditions.extend(
            {
                "ruleset_version": ruleset_version,
                "rule_id": rule.rule_id,
                "condition": condition,
            }
            for condition in rule.relevant_conditions
        )
    return definitions, predicates, cohort_conditions
