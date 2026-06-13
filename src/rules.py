import hashlib
import json

from src.config import Rule


OPERATOR_LABELS = {
    "greater_than_or_equal": "at or above",
    "less_than_or_equal": "at or below",
}


def compile_rules(rules: list[Rule]) -> tuple[list[dict], list[dict]]:
    canonical = json.dumps(
        [rule.model_dump(mode="json") for rule in rules],
        sort_keys=True,
        separators=(",", ":"),
    )
    ruleset_version = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    definitions: list[dict] = []
    conditions: list[dict] = []

    for rule in rules:
        for city_id in rule.cities:
            for month in rule.months:
                definitions.append(
                    {
                        "ruleset_version": ruleset_version,
                        "rule_id": rule.rule_id,
                        "city_id": city_id,
                        "month": month,
                        "metric": rule.metric,
                        "operator": rule.operator,
                        "operator_label": OPERATOR_LABELS[rule.operator],
                        "threshold": rule.threshold,
                        "persistence_hours": rule.persistence_hours,
                        "severity": rule.severity,
                    }
                )
        conditions.extend(
            {
                "ruleset_version": ruleset_version,
                "rule_id": rule.rule_id,
                "condition": condition,
            }
            for condition in rule.relevant_conditions
        )
    return definitions, conditions

