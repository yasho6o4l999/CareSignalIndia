import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import yaml

from src.config import (
    CONFIG_ROOT,
    Condition,
    PublicationPolicy,
    Rule,
    RuntimeSettings,
    _deep_merge,
)


FindingLevel = Literal["error", "warning"]


@dataclass(frozen=True)
class ConflictFinding:
    level: FindingLevel
    kind: str
    rule_ids: tuple[str, ...]
    cities: tuple[str, ...]
    months: tuple[int, ...]
    detail: str


@dataclass(frozen=True)
class ConfigurationSnapshot:
    rules: tuple[Rule, ...]
    condition_profiles: dict[str, dict[Condition, str]]
    publication_policy: PublicationPolicy
    runtime_settings: RuntimeSettings
    city_ids: tuple[str, ...]


@dataclass(frozen=True)
class ImpactReport:
    added_rules: tuple[str, ...]
    removed_rules: tuple[str, ...]
    changed_rules: tuple[str, ...]
    added_cities: tuple[str, ...]
    removed_cities: tuple[str, ...]
    affected_cities: tuple[str, ...]
    city_month_scopes_added: int
    city_month_scopes_removed: int
    condition_links_added: int
    condition_links_removed: int
    severity_bands_added: int
    severity_bands_removed: int
    estimated_members_in_affected_cities: int
    publication_policy_changed: bool
    runtime_settings_changed: bool


def _read_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_snapshot(config_root: Path) -> ConfigurationSnapshot:
    profiles = _read_yaml(config_root / "condition_relevance.yml")["profiles"]
    detection_rules = _read_yaml(config_root / "regional_rules.yml")["rules"]
    catalog = _read_yaml(config_root / "signal_catalog.yml")["signals"]
    detection_ids = {item["rule_id"] for item in detection_rules}
    if set(catalog) != detection_ids:
        raise ValueError("signal catalog and regional rules must contain exactly the same rule IDs")
    rules = tuple(
        Rule.model_validate(_deep_merge(item, catalog[item["rule_id"]]))
        for item in detection_rules
    )
    city_ids = tuple(
        sorted(
            item["city_id"]
            for item in _read_yaml(config_root / "cities.yml")["cities"]
            if item.get("enabled", True)
        )
    )
    runtime_settings = RuntimeSettings.model_validate(_read_yaml(config_root / "runtime.yml"))
    if runtime_settings.enabled_cities is not None:
        city_ids = tuple(sorted(set(city_ids) & set(runtime_settings.enabled_cities)))
    return ConfigurationSnapshot(
        rules=rules,
        condition_profiles=profiles,
        publication_policy=PublicationPolicy.model_validate(
            _read_yaml(config_root / "publication_policy.yml")
        ),
        runtime_settings=runtime_settings,
        city_ids=city_ids,
    )


def _predicate_key(predicate) -> str:
    return json.dumps(predicate.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def _predicate_dimension(predicate) -> tuple:
    return (
        predicate.metric,
        predicate.operator,
        predicate.comparison,
        predicate.aggregation.function,
        predicate.aggregation.window_hours,
    )


def _rule_conditions(rule: Rule, profiles: dict[str, dict[Condition, str]]) -> set[str]:
    return set(profiles[rule.condition_profile])


def detect_rule_conflicts(
    rules: list[Rule] | tuple[Rule, ...],
    condition_profiles: dict[str, dict[Condition, str]],
) -> list[ConflictFinding]:
    findings: list[ConflictFinding] = []
    for rule in rules:
        bounds: dict[tuple[str, str, int | None], dict[str, float]] = {}
        for predicate in rule.predicates:
            if predicate.comparison != "absolute":
                continue
            key = (
                predicate.metric,
                predicate.aggregation.function,
                predicate.aggregation.window_hours,
            )
            bounds.setdefault(key, {})[predicate.operator] = predicate.threshold
        for key, operators in bounds.items():
            lower = operators.get("greater_than_or_equal")
            upper = operators.get("less_than_or_equal")
            if lower is not None and upper is not None and lower > upper:
                findings.append(
                    ConflictFinding(
                        level="error",
                        kind="impossible_predicate_range",
                        rule_ids=(rule.rule_id,),
                        cities=tuple(sorted(rule.cities)),
                        months=tuple(sorted(rule.months)),
                        detail=f"{key[0]} requires a value at or above {lower} and at or below {upper}.",
                    )
                )

    for index, left in enumerate(rules):
        for right in rules[index + 1:]:
            cities = tuple(sorted(set(left.cities) & set(right.cities)))
            months = tuple(sorted(set(left.months) & set(right.months)))
            conditions = _rule_conditions(left, condition_profiles) & _rule_conditions(
                right, condition_profiles
            )
            if not cities or not months or not conditions:
                continue
            left_predicates = {_predicate_key(predicate) for predicate in left.predicates}
            right_predicates = {_predicate_key(predicate) for predicate in right.predicates}
            left_dimensions = {_predicate_dimension(predicate) for predicate in left.predicates}
            right_dimensions = {_predicate_dimension(predicate) for predicate in right.predicates}
            if left_predicates == right_predicates:
                findings.append(
                    ConflictFinding(
                        level="error",
                        kind="duplicate_signal_scope",
                        rule_ids=(left.rule_id, right.rule_id),
                        cities=cities,
                        months=months,
                        detail="Rules have identical predicates and overlapping regional, calendar, and cohort scope.",
                    )
                )
            elif left_predicates < right_predicates or right_predicates < left_predicates:
                findings.append(
                    ConflictFinding(
                        level="warning",
                        kind="nested_signal_overlap",
                        rule_ids=(left.rule_id, right.rule_id),
                        cities=cities,
                        months=months,
                        detail=(
                            "One rule's predicates are a subset of the other; both signals may target "
                            f"the same members for conditions {sorted(conditions)}."
                        ),
                    )
                )
            elif left_dimensions == right_dimensions:
                findings.append(
                    ConflictFinding(
                        level="warning",
                        kind="threshold_signal_overlap",
                        rule_ids=(left.rule_id, right.rule_id),
                        cities=cities,
                        months=months,
                        detail=(
                            "Rules evaluate the same metric and operator dimensions with different "
                            "thresholds; the broader signal may overlap the narrower signal."
                        ),
                    )
                )
    return findings


def _rule_scopes(rule: Rule) -> set[tuple[str, int]]:
    return {(city, month) for city in rule.cities for month in rule.months}


def _condition_links(
    rule: Rule, profiles: dict[str, dict[Condition, str]]
) -> set[tuple[str, str, int, str]]:
    return {
        (rule.rule_id, city, month, condition)
        for city, month in _rule_scopes(rule)
        for condition in _rule_conditions(rule, profiles)
    }


def _severity_bands(rule: Rule) -> set[tuple[str, str, int, float]]:
    if rule.severity_bands:
        return {
            (
                rule.rule_id,
                band.severity,
                band.minimum_persistence_hours,
                band.minimum_threshold_ratio,
            )
            for band in rule.severity_bands
        }
    return {(rule.rule_id, rule.severity, rule.persistence_hours, 1.0)}


def compare_snapshots(
    baseline: ConfigurationSnapshot,
    candidate: ConfigurationSnapshot,
) -> ImpactReport:
    baseline_rules = {rule.rule_id: rule for rule in baseline.rules}
    candidate_rules = {rule.rule_id: rule for rule in candidate.rules}
    common = baseline_rules.keys() & candidate_rules.keys()
    changed = {
        rule_id
        for rule_id in common
        if baseline_rules[rule_id].model_dump(mode="json")
        != candidate_rules[rule_id].model_dump(mode="json")
        or _rule_conditions(baseline_rules[rule_id], baseline.condition_profiles)
        != _rule_conditions(candidate_rules[rule_id], candidate.condition_profiles)
    }
    baseline_scopes = {
        (rule.rule_id, city, month)
        for rule in baseline.rules
        for city, month in _rule_scopes(rule)
    }
    candidate_scopes = {
        (rule.rule_id, city, month)
        for rule in candidate.rules
        for city, month in _rule_scopes(rule)
    }
    baseline_links = {
        link for rule in baseline.rules for link in _condition_links(rule, baseline.condition_profiles)
    }
    candidate_links = {
        link for rule in candidate.rules for link in _condition_links(rule, candidate.condition_profiles)
    }
    baseline_bands = {band for rule in baseline.rules for band in _severity_bands(rule)}
    candidate_bands = {band for rule in candidate.rules for band in _severity_bands(rule)}
    affected_rule_ids = changed | (baseline_rules.keys() ^ candidate_rules.keys())
    affected_cities = {
        city
        for rule_id in affected_rule_ids
        for city in (
            set(baseline_rules[rule_id].cities) if rule_id in baseline_rules else set()
        )
        | (set(candidate_rules[rule_id].cities) if rule_id in candidate_rules else set())
    } | (set(baseline.city_ids) ^ set(candidate.city_ids))
    if baseline.runtime_settings != candidate.runtime_settings:
        affected_cities |= set(baseline.city_ids) | set(candidate.city_ids)
    weights = candidate.runtime_settings.synthetic_members.city_weights
    enabled_weights = {city: weights.get(city, 1.0) for city in candidate.city_ids}
    total_weight = sum(enabled_weights.values())
    estimated_members = round(
        candidate.runtime_settings.synthetic_members.member_count
        * sum(enabled_weights.get(city, 0) for city in affected_cities)
        / total_weight
    ) if total_weight else 0
    return ImpactReport(
        added_rules=tuple(sorted(candidate_rules.keys() - baseline_rules.keys())),
        removed_rules=tuple(sorted(baseline_rules.keys() - candidate_rules.keys())),
        changed_rules=tuple(sorted(changed)),
        added_cities=tuple(sorted(set(candidate.city_ids) - set(baseline.city_ids))),
        removed_cities=tuple(sorted(set(baseline.city_ids) - set(candidate.city_ids))),
        affected_cities=tuple(sorted(affected_cities)),
        city_month_scopes_added=len(candidate_scopes - baseline_scopes),
        city_month_scopes_removed=len(baseline_scopes - candidate_scopes),
        condition_links_added=len(candidate_links - baseline_links),
        condition_links_removed=len(baseline_links - candidate_links),
        severity_bands_added=len(candidate_bands - baseline_bands),
        severity_bands_removed=len(baseline_bands - candidate_bands),
        estimated_members_in_affected_cities=estimated_members,
        publication_policy_changed=baseline.publication_policy != candidate.publication_policy,
        runtime_settings_changed=baseline.runtime_settings != candidate.runtime_settings,
    )


def _print_conflicts(findings: list[ConflictFinding], as_json: bool) -> None:
    if as_json:
        print(json.dumps([asdict(finding) for finding in findings], indent=2))
        return
    print(f"Rule review: errors={sum(f.level == 'error' for f in findings)} warnings={sum(f.level == 'warning' for f in findings)}")
    for finding in findings:
        print(
            f"- {finding.level.upper()} {finding.kind}: {', '.join(finding.rule_ids)}; "
            f"cities={list(finding.cities)} months={list(finding.months)}; {finding.detail}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Review CareSignal configuration changes.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    conflicts = subparsers.add_parser("conflicts", help="Detect conflicting and overlapping rules.")
    conflicts.add_argument("--config", type=Path, default=CONFIG_ROOT)
    conflicts.add_argument("--json", action="store_true")
    impact = subparsers.add_parser("impact", help="Compare a baseline config directory with a candidate.")
    impact.add_argument("--baseline", type=Path, required=True)
    impact.add_argument("--candidate", type=Path, default=CONFIG_ROOT)
    impact.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.command == "conflicts":
        snapshot = load_snapshot(args.config)
        findings = detect_rule_conflicts(snapshot.rules, snapshot.condition_profiles)
        _print_conflicts(findings, args.json)
        raise SystemExit(1 if any(finding.level == "error" for finding in findings) else 0)

    report = compare_snapshots(load_snapshot(args.baseline), load_snapshot(args.candidate))
    payload = asdict(report)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("Configuration impact:")
        for key, value in payload.items():
            print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
