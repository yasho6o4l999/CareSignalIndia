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
| `incremental_policy.yml` | Forecast correction lookback plus raw compaction batch, row-group, and compression settings |
| `extraction_policy.yml` | Source-specific concurrency, timeouts, retries, response contracts, and record-acceptance thresholds |
| `quality_policy.yml` | Source coverage/freshness, join-loss, anomaly, and cross-mart integrity thresholds |
| `runtime.yml` | Decision timezone, analytical-history retention, synthetic-member count, seed, and regional distribution |

`python -m src.validate_config` validates governed vocabularies, duplicate dimensions and predicates,
cross-file city/profile/rule references, publication feasibility, and runtime city references before an ETL
run starts.

Each run stores a deterministic `configuration_version` in SQLite. Compiled regional-rule Parquet files also
carry a deterministic `ruleset_version`, while synthetic members carry a version derived from generator
settings and city weights.

DuckDB calculates configured rolling metrics before evaluating predicates. Qualified persistence windows
join to compiled severity bands and select the highest matching severity. The prioritization queue applies
condition relevance, age, and outreach consent. The assignment does not model completed outreach actions or
contact-frequency policies.

## Pre-Deployment Review

Rule conflict review detects impossible absolute ranges and duplicate signals with overlapping city, month,
and cohort scope. Those findings exit with a failure code suitable for CI. Nested compound signals are
reported as warnings because they may be intentional but can create duplicate care-team workload.

```bash
python -m src.config_review conflicts
python -m src.config_review conflicts --json
```

Configuration impact analysis compares two complete configuration directories. It reports added, removed,
and changed rules and cities; city-month evaluation scope; cohort links; severity bands; policy changes; and
the estimated synthetic-member population in affected cities.

```bash
cp -R config /tmp/caresignal-config-baseline
# edit config/
python -m src.config_review impact --baseline /tmp/caresignal-config-baseline
python -m src.config_review impact --baseline /tmp/caresignal-config-baseline --json
```

The impact report is structural and deterministic. A production release process should additionally replay
the candidate rules against representative historical data to estimate alert volume and care-team workload.
