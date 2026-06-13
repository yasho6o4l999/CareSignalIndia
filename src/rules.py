import hashlib
import json

from src.config import Rule, SeverityBand, load_condition_profiles


OPERATOR_LABELS = {
    "greater_than_or_equal": "at or above",
    "less_than_or_equal": "at or below",
}


def compile_rules(rules: list[Rule]) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    canonical = json.dumps(
        [rule.model_dump(mode="json") for rule in rules],
        sort_keys=True,
        separators=(",", ":"),
    )
    ruleset_version = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    definitions: list[dict] = []
    predicates: list[dict] = []
    cohort_conditions: list[dict] = []
    severity_bands: list[dict] = []
    profiles = load_condition_profiles()

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
                        "signal_name": rule.name,
                        "signal_description": rule.description,
                        "signal_category": rule.category,
                        "owner": rule.owner,
                        "status": rule.status,
                        "rationale": rule.rationale,
                        "source_references": json.dumps(
                            [reference.model_dump(mode="json") for reference in rule.source_references],
                            sort_keys=True,
                        ),
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
                    "aggregation_function": predicate.aggregation.function,
                    "aggregation_window_hours": predicate.aggregation.window_hours,
                }
            )
        conditions = profiles[rule.condition_profile]
        cohort_conditions.extend(
            {
                "ruleset_version": ruleset_version,
                "rule_id": rule.rule_id,
                "condition": condition,
                "relevance": relevance,
            }
            for condition, relevance in conditions.items()
        )
        bands = rule.severity_bands or [
            SeverityBand(
                severity=rule.severity,
                minimum_persistence_hours=rule.persistence_hours,
                minimum_threshold_ratio=1.0,
            )
        ]
        severity_bands.extend(
            {
                "ruleset_version": ruleset_version,
                "rule_id": rule.rule_id,
                "severity": band.severity,
                "minimum_persistence_hours": band.minimum_persistence_hours,
                "minimum_threshold_ratio": band.minimum_threshold_ratio,
                "severity_rank": {"low": 1, "medium": 2, "high": 3, "critical": 4}[
                    band.severity
                ],
            }
            for band in bands
        )
    return definitions, predicates, cohort_conditions, severity_bands
