# Configuration Layer

The configuration layer separates business intent from pipeline code and produces deterministic, traceable
runtime inputs.

| File | Responsibility |
|---|---|
| `cities.yml` | Enabled regions, coordinates, climate zones, criticality, languages, and expected sources |
| `regional_rules.yml` | Detection predicates, aggregation semantics, persistence, cities, and calendar applicability |
| `signal_catalog.yml` | Governed signal name, description, category, owner, rationale, evidence, condition profile, and severity bands |
| `condition_relevance.yml` | Reusable chronic-condition relevance profiles |
| `publication_policy.yml` | Required sources, freshness limits, minimum coverage, and mandatory cities |
| `incremental_policy.yml` | Forecast correction lookback |
| `outreach_policy.yml` | Contact cooldown and future severity-escalation behavior |
| `runtime.yml` | Synthetic-member count, seed, and regional distribution |
| `environments/*.yml` | Environment-specific overrides |

`python -m src.validate_config` validates governed vocabularies, duplicate dimensions and predicates,
cross-file city/profile/rule references, publication feasibility, and runtime city references before an ETL
run starts.

Each run stores a deterministic `configuration_version` in SQLite. Compiled regional-rule Parquet files also
carry a deterministic `ruleset_version`, while synthetic members carry a version derived from generator
settings and city weights.

DuckDB calculates configured rolling metrics before evaluating predicates. Qualified persistence windows
join to compiled severity bands and select the highest matching severity. The outreach queue applies
condition relevance, age, consent, and the configured contact cooldown.

`repeat_when_severity_increases` is intentionally not enforced in this prototype because there is no
persisted outreach-action history. In production, that policy should compare the new trigger severity with
the member's most recent action for the same signal before overriding the cooldown.
