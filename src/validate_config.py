from src.config import (
    configuration_version,
    load_cities,
    load_condition_profiles,
    load_incremental_policy,
    load_extraction_policy,
    load_outreach_policy,
    load_publication_policy,
    load_quality_policy,
    load_rules,
    load_runtime_settings,
)
from src.rules import compile_rules
from src.config_review import detect_rule_conflicts


def main() -> None:
    cities = load_cities()
    rules = load_rules()
    definitions, predicates, conditions, severity_bands = compile_rules(rules)
    load_publication_policy()
    load_incremental_policy()
    load_extraction_policy()
    load_outreach_policy()
    load_quality_policy()
    load_runtime_settings()
    conflicts = detect_rule_conflicts(rules, load_condition_profiles())
    errors = [finding for finding in conflicts if finding.level == "error"]
    if errors:
        raise ValueError(f"Configuration contains {len(errors)} rule conflicts: {errors}")
    print(
        "Configuration valid: "
        f"version={configuration_version()} cities={len(cities)} rules={len(rules)} "
        f"definitions={len(definitions)} predicates={len(predicates)} "
        f"condition_links={len(conditions)} severity_bands={len(severity_bands)} "
        f"overlap_warnings={sum(finding.level == 'warning' for finding in conflicts)}"
    )


if __name__ == "__main__":
    main()
