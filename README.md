# CareSignal India

CareSignal India is a year-round environmental care-intelligence prototype for digital therapeutics care-operations teams. It combines public environmental forecasts with deterministic synthetic chronic-care member data to create explainable, consent-aware outreach queues.

The initial vertical slice supports Delhi, Mumbai, Bengaluru, Chennai, and Ahmedabad. It models heat, cold, heavy-rain, and particulate-pollution triggers, including a Delhi winter-pollution rule.
The regional catalog now also includes Lucknow and Jaipur, plus compound scenarios for monsoon disruption,
northeast-monsoon rain and wind, coastal heat-humidity stress, sustained Ahmedabad daytime and nighttime
heat, coastal high-wind disruption, winter cold-plus-pollution exposure, and Jaipur temperature swings.

## Architecture

- Bounded asynchronous API extraction with connection pooling, timeouts, and retries
- Pydantic schema and accepted-range validation
- Partitioned, ZSTD-compressed Parquet storage
- DuckDB transformations directly over Parquet
- Predicate pushdown in dashboard queries
- Five-year NASA POWER historical baselines with city/month p90 and p95 thresholds
- Deterministic synthetic members with consent controls
- Machine-readable freshness, uniqueness, and non-empty quality checks
- Configuration-driven regional rules with consecutive-hour persistence windows

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

Regional rules are maintained in `config/regional_rules.yml`. Each ETL run compiles them into normalized
rule-definition and rule-condition Parquet datasets with a deterministic ruleset version. DuckDB evaluates
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

Synthetic members are cached by generator and city-set version under `data/reference/synthetic_members/`.
Compiled regional rules are cached by deterministic ruleset hash under `data/reference/regional_rules/`.
Forecast-driven marts remain immutable per-run snapshots.

Marts are built under a staging directory. Source quality checks and final publication-contract checks must
pass before the directory is atomically published. Failed runs remain recorded in SQLite and never replace
the latest successful dashboard run. The local retention policy keeps the five newest forecast/raw and
processed snapshots while preserving SQLite run history and reusable reference datasets.

Publication readiness is configured in `config/publication_policy.yml`. A city is complete only when weather,
air-quality, and historical-baseline data are available. Seven complete cities produces `success`; at least
five complete cities produces `partial_success`; fewer than five prevents publication. Isolated source-city
failures are quarantined, shown in the dashboard, and do not advance their previous successful watermarks.

Forecast snapshots are incrementally merged using each source-city `latest_successful_run` watermark. Because
Open-Meteo exposes revision-prone rolling forecasts rather than a change-data feed, every run retrieves the
current forecast window, compares it with the previous successful snapshot in DuckDB, and classifies natural
keys as inserted, updated, or unchanged. Unchanged records retain their original extraction metadata,
corrections replace prior values, and records older than the configurable correction lookback in
`config/incremental_policy.yml` are pruned. SQLite stores both source-city and run-level change metrics.

Synthetic member data contains no names, contact details, exact addresses, or real identifiers. Outreach priority is an operational demonstration, not a clinical risk score.

## Scheduling

The required reviewer workflow is manual. `deployment/crontab.example` demonstrates a six-hour production-style refresh schedule. A real deployment should additionally use an overlap lock, managed secrets, monitoring, and alerting.

## Current Limitations

- Open-Meteo provides modeled air-quality forecasts rather than ground-station observations.
- No messages are sent; the project only generates stakeholder and outreach queues.
- The scheduler example is not installed automatically.

## Next Improvements

- Add quarantined-record outputs and partial-source publication
- Add extraction manifests and incremental retention policies
- Add mocked API integration tests and query-plan benchmarks
