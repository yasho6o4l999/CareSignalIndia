# CareSignal India

CareSignal India is a year-round environmental care-intelligence prototype for digital therapeutics care-operations teams. It combines public environmental forecasts with deterministic synthetic chronic-care member data to create explainable, consent-aware outreach queues.

The initial vertical slice supports Delhi, Mumbai, Bengaluru, Chennai, and Ahmedabad. It models heat, cold, heavy-rain, and particulate-pollution triggers, including a Delhi winter-pollution rule.
The regional catalog now also includes Lucknow and Jaipur, plus compound scenarios for monsoon disruption,
northeast-monsoon rain and wind, coastal heat-humidity stress, sustained Ahmedabad daytime and nighttime
heat, coastal high-wind disruption, winter cold-plus-pollution exposure, and Jaipur temperature swings.

## Architecture

- Bounded asynchronous API extraction with connection pooling, timeouts, and retries
- Source-specific concurrency, timeout, retry, and response-contract policies
- Pydantic schema and accepted-range validation
- Per-record salvage with structured field-level quarantine and configurable valid-ratio gates
- Partitioned, manifested Parquet storage with source-level compaction for analytical reads
- DuckDB transformations directly over Parquet
- Predicate pushdown in dashboard queries
- Five-year NASA POWER historical baselines with city/month p90 and p95 thresholds
- Deterministic synthetic members with consent controls
- Config-driven source checks, cross-source reconciliation, cross-mart integrity, and historical anomalies
- Configuration-driven regional rules with consecutive-hour persistence windows
- Decision-timezone-aware separation of today's actions and upcoming forecast risks
- Governed signal catalog, condition-relevance profiles, dynamic severity bands, and outreach cooldown
- Environment overrides and deterministic configuration lineage stored with every pipeline run

See [`docs/architecture.md`](docs/architecture.md) for the current high-level and low-level architecture
diagrams, component contracts, review sequence, and explicit boundary between implemented capabilities and
future operational work.
See [`docs/staging-and-quality.md`](docs/staging-and-quality.md) for quality gates, profile baselines, and
reconciliation semantics.

No pandas dependency is used. Generated data and credentials are excluded from Git.

## Run Locally

Use Python 3.11, 3.12, or 3.13. Python 3.12 is recommended.

```bash
git clone <repository-url>
cd <repository-folder>
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python etl.py
streamlit run app.py
```

## Data Sources

- Open-Meteo Weather Forecast API: https://open-meteo.com/en/docs
- Open-Meteo Air Quality API: https://open-meteo.com/en/docs/air-quality-api
- NASA POWER Daily API: https://power.larc.nasa.gov/docs/services/api/temporal/daily/

Open-Meteo's free endpoint is intended for non-commercial use. This repository is an educational candidate assignment.

## Data Model

Raw datasets are partitioned by `source` and `run_id`. DuckDB builds:

- `city_conditions.parquet`
- `historical_baselines.parquet`
- `active_triggers.parquet`
- `outreach_queue.parquet`
- `stakeholder_alerts.parquet`
- `quality_results.parquet`

Each qualifying trigger is classified using `config/runtime.yml` as either `today_action` when its forecast
window begins on the decision date, or `upcoming_risk` when it begins later. The dashboard presents these as
separate operational queues.

Regional detection rules are maintained in `config/regional_rules.yml`; governed descriptions, rationale,
ownership, evidence links, condition profiles, and severity bands live in `config/signal_catalog.yml`.
Each ETL run compiles them into normalized rule-definition, predicate, condition-relevance, and severity-band
Parquet datasets with a deterministic ruleset version. DuckDB evaluates
the applicable city, calendar month, metric, threshold, and operator. A trigger is published only after the
configured number of consecutive hourly breaches; missing hours and non-breaching values break the streak.

Rules may use either a fixed absolute threshold or a city/month historical percentile. The initial
`locally_unusual_heat` rule compares hourly forecast temperature against the city's p95 historical daily
maximum temperature for the matching calendar month, calculated from the previous five complete years.
Absolute heat rules remain separate because a locally unusual condition and an absolute severe condition
represent different operational signals.

Rules may contain multiple environmental predicates. Every predicate must be satisfied during the same
forecast hour before the rule-level persistence clock advances. This supports compound scenarios without
hardcoding city-specific logic into SQL.

The configuration layer is validated independently with:

```bash
python -m src.validate_config
python -m src.config_review conflicts
```

Before deploying config changes, `python -m src.config_review impact --baseline <config-directory>`
quantifies changed rule scope, cohorts, severity bands, policies, and estimated affected members. See
[`docs/configuration.md`](docs/configuration.md) for the review workflow and CI behavior.

`config/runtime.yml` owns the decision timezone and deterministic synthetic-member settings,
`config/publication_policy.yml` owns
source-aware publication gates, `config/outreach_policy.yml` owns contact cooldown, and
`config/environments/` contains environment-specific overrides selected by `CARESIGNAL_ENV`.

### Regional Scenario Catalog

| Scenario | Region | Evidence required |
|---|---|---|
| Winter particulate pollution | Delhi | Sustained PM2.5 during October-January |
| Monsoon disruption | Mumbai | Daily rainfall above the local p95 during June-September |
| Northeast-monsoon disruption | Chennai | Local p95 daily rainfall combined with high wind |
| Coastal heat-humidity stress | Mumbai and Chennai | High apparent-temperature uplift combined with high humidity |
| Sustained daytime and nighttime heat | Ahmedabad | Local p95 daily maximum combined with local p90 daily minimum |
| Coastal high-wind disruption | Mumbai and Chennai | Local p90 daily rainfall combined with high wind |
| Winter cold-pollution compound | Delhi and Lucknow | Elevated PM2.5 combined with temperature below local p10 |
| Temperature swing | Jaipur | Daily temperature range above local p95 |
| Locally unusual heat | All supported cities | Temperature above the matching city/month p95 |

The five-year NASA POWER backfill is cached under a `baseline_end_year` partition. Six-hour forecast runs
reuse that snapshot, and a new historical snapshot is fetched only when a new complete calendar year becomes
available or the local cache is removed.

## SQL Ownership

All executable DuckDB SQL is versioned under `sql/` rather than embedded in Python:

- `sql/marts/`: raw-to-analytical transformations and published marts
- `sql/quality/`: source profiling and data-quality queries
- `sql/dashboard/`: Streamlit read queries
- `sql/common/`: reusable utility queries

Python resolves trusted local paths, binds runtime filter values, and executes the named SQL artifacts.

## Operational Metadata

SQLite at `data/metadata/pipeline.db` is the authoritative operational state store. It records pipeline runs,
source-city readiness, watermarks, invalid records, and published-dataset lineage. The dashboard selects the
latest published run from SQLite; `latest_run.json` is no longer used.

The normalized control-plane schema separates run identity from run metrics, combines each source-city
execution with its resulting watermark, unifies artifact metadata and lineage, and persists quality results.
See [`docs/operational-metadata.md`](docs/operational-metadata.md) for the model and migration boundary.

Synthetic member dimensions are incrementally reconciled in SQLite with SCD Type 2 history, deactivation,
condition-link change tracking, and separate outreach activity. A configured generation anchor date
ensures identical configuration produces identical members across execution dates. The current dimensions
are exported from SQLite into immutable, city-partitioned analytical snapshots under
`data/reference/member_snapshots/`.

Each content-addressed member snapshot rebuilds only changed city partitions and is published atomically
after its manifest validates file checksums, schemas, row
counts, unique member IDs, and member-condition referential integrity. Snapshot metadata and checksums are
registered in SQLite, and every pipeline run records the exact `member_snapshot_id` it used.
Retention protects every snapshot referenced by a published run and removes only older unreferenced versions.
Compiled regional rules are cached by deterministic ruleset hash under `data/reference/regional_rules/`.
Forecast-driven marts remain immutable per-run snapshots.

Marts are built under a staging directory. Source quality checks, forecast join reconciliation, and cross-mart
integrity checks must pass before the directory is atomically published. Historical quality profiles establish
anomaly baselines; failed-run profiles are excluded from future comparisons. Failed runs remain recorded in SQLite and never replace
the latest successful dashboard run. The local retention policy keeps the five newest forecast/raw and
processed snapshots while preserving SQLite run history and reusable reference datasets.

Publication readiness is configured in `config/publication_policy.yml`. A city is complete only when its
expected required sources are available and within the source-specific freshness limit. Mandatory cities
must be complete for partial publication. Seven complete cities produces `success`; at least five complete
cities including all mandatory cities produces `partial_success`; otherwise publication is prevented. Isolated source-city
failures are quarantined, shown in the dashboard, and do not advance their previous successful watermarks.

Forecast snapshots are incrementally merged using each source-city `latest_successful_run` watermark. Because
Open-Meteo exposes revision-prone rolling forecasts rather than a change-data feed, every run retrieves the
current forecast window, compares it with the previous successful snapshot in DuckDB, and classifies natural
keys as inserted, updated, or unchanged. Unchanged records retain their original extraction metadata,
corrections replace prior values, and records older than the configurable correction lookback in
`config/incremental_policy.yml` are pruned. SQLite stores both source-city and run-level change metrics.

Source-specific extraction behavior is configured in `config/extraction_policy.yml`. HTTP metrics capture
duration, attempts, response size, status, and response code per source-city request. Non-transient client
errors are not retried, while transient errors use bounded exponential backoff and respect `Retry-After`.

Validated forecast outputs publish through source-city staging paths. Each raw Parquet file has a manifest
containing schema governance, semantic content hash, checksum, column statistics, row-group details, timestamp
range, and reuse lineage. When merged environmental content is unchanged, the new run hard-links the previous
file rather than storing duplicate bytes while still retaining a complete immutable run view. Source-city
files are then streamed into one compacted file per forecast source and run; quality checks and marts read
the compacted artifacts to avoid DuckDB small-file overhead.

Synthetic member data contains no names, contact details, exact addresses, or real identifiers. Outreach priority is an operational demonstration, not a clinical risk score.

## Scheduling

The required reviewer workflow is manual. `deployment/crontab.example` demonstrates a six-hour production-style refresh schedule. A real deployment should additionally use an overlap lock, managed secrets, monitoring, and alerting.

## Current Limitations

- Open-Meteo provides modeled air-quality forecasts rather than ground-station observations.
- No messages are sent; the project only generates stakeholder and outreach queues.
- Severity-escalation repeat outreach is configured but requires production action-history data before it can be enforced.
- The synthetic source emits full extracts; production ingestion should consume source-native incremental member changes.
- The scheduler example is not installed automatically.

## Next Improvements

- Expand anomaly detection beyond row counts to field distributions and validation-pattern trends
- Add alert routing for repeated source degradation and quarantine-volume spikes
- Add query-plan benchmarks
