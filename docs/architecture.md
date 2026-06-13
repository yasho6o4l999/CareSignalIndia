# CareSignal India Architecture

This document describes the architecture implemented in the repository today. Scheduling, automated recovery,
external monitoring, notifications, and dashboard redesign are intentionally shown as future work rather than
current capabilities.

## High-Level Architecture

```mermaid
flowchart LR
    subgraph Sources["Public Environmental Sources"]
        Weather["Open-Meteo Weather Forecast"]
        Air["Open-Meteo Air Quality Forecast"]
        History["NASA POWER Daily History"]
    end

    subgraph Control["Configuration and Reference Plane"]
        Cities["City Catalog"]
        Policies["Incremental and Publication Policies"]
        RuleConfig["Regional Rule Configuration"]
        RuleReference["Versioned Compiled Rules"]
        MemberReference["Versioned Synthetic Members"]
    end

    subgraph Pipeline["Local Data Engineering Pipeline"]
        Extract["Async Extraction and Schema Validation"]
        Incremental["Watermark-Driven Incremental Merge"]
        Quality["Source Quality and Readiness Gates"]
        Decisioning["DuckDB Baselines, Rules, and Persistence Evaluation"]
        Publish["Publication Contract and Atomic Publish"]
    end

    subgraph Storage["Local Persistence"]
        Raw["Immutable Run-Partitioned Parquet Snapshots"]
        Marts["Published Analytical Parquet Marts"]
        SQLite["SQLite Operational Metadata"]
        Quarantine["Invalid Record Quarantine"]
    end

    subgraph Product["Care Operations Product"]
        Dashboard["Streamlit Dashboard"]
        Stakeholders["Care Operations Stakeholders"]
    end

    Weather --> Extract
    Air --> Extract
    History --> Extract
    Cities --> Extract
    Policies --> Incremental
    Policies --> Quality
    RuleConfig --> RuleReference
    Cities --> MemberReference
    RuleReference --> Decisioning
    MemberReference --> Decisioning
    Extract --> Incremental
    Incremental --> Raw
    Raw --> Quality
    Quality --> Decisioning
    Decisioning --> Publish
    Publish --> Marts
    Extract --> Quarantine
    Incremental <--> SQLite
    Quality --> SQLite
    Publish --> SQLite
    Marts --> Dashboard
    SQLite --> Dashboard
    Dashboard --> Stakeholders

    Future["Future: Scheduling, Recovery, Monitoring, and Notifications"]
    Future -.-> Pipeline
```

### High-Level Responsibilities

| Area | Current responsibility |
|---|---|
| Public sources | Provide seven-day weather and air-quality forecasts plus five complete years of historical weather |
| Configuration and reference plane | Defines supported cities, regional scenarios, publication thresholds, correction lookback, compiled rules, and synthetic members |
| Pipeline | Extracts concurrently, validates schemas, merges rolling snapshots, evaluates readiness, builds analytical marts, and publishes atomically |
| Parquet | Stores memory-efficient source snapshots, reusable references, historical partitions, and immutable published marts |
| SQLite | Drives pipeline state through run lifecycle, source readiness, watermarks, invalid records, incremental metrics, and publication lineage |
| Streamlit | Reads only the latest successfully published run and exposes care-operations outputs plus pipeline-health information |

## Low-Level Architecture

```mermaid
flowchart TD
    Start["Manual Entry Point: python etl.py"] --> LoadConfig["Load cities.yml, regional_rules.yml, publication_policy.yml, incremental_policy.yml"]
    LoadConfig --> MetadataInit["MetadataStore initializes SQLite migrations"]
    MetadataInit --> StartRun["Insert pipeline_runs status=running"]

    LoadConfig --> EnsureReferences["Ensure versioned reference datasets"]
    EnsureReferences --> CompileRules["Compile regional rules and ruleset hash"]
    EnsureReferences --> GenerateMembers["Generate deterministic synthetic members"]
    CompileRules --> RuleParquet["data/reference/regional_rules"]
    GenerateMembers --> MemberParquet["data/reference/synthetic_members"]

    StartRun --> ForecastExtract["OpenMeteoClient async weather and air-quality requests per city"]
    StartRun --> HistoryCheck["Check NASA historical cache per city"]
    HistoryCheck -->|Missing cache| HistoryExtract["NasaPowerClient async historical requests"]
    HistoryCheck -->|Cache available| HistoryReady["Record cached source readiness"]
    HistoryExtract --> HistoryParquet["data/raw/source=nasa_power_daily partitioned by baseline year, city, and year"]

    ForecastExtract --> Pydantic["Pydantic type, range, and timezone validation"]
    Pydantic -->|Source-city failure| Quarantine["SQLite invalid_records and failed source_readiness"]
    Pydantic -->|Valid records| WatermarkRead["Read latest_successful_run watermark per source and city"]
    WatermarkRead --> PreviousSnapshot["Locate previous successful Parquet snapshot"]
    PreviousSnapshot --> IncrementalSQL["DuckDB deduplicate, compare, and merge with correction lookback"]
    IncrementalSQL --> ChangeMetrics["Inserted, updated, unchanged, and rejected metrics"]
    IncrementalSQL --> RawSnapshot["data/raw/source=open_meteo_*/run_id/city.parquet"]
    ChangeMetrics --> SourceReadiness["SQLite source_readiness"]

    HistoryReady --> ReadinessDecision["Evaluate required-source completeness by city"]
    HistoryParquet --> ReadinessDecision
    SourceReadiness --> ReadinessDecision
    ReadinessDecision -->|Fewer than minimum complete cities| FailedRun["Mark failed; do not publish"]
    ReadinessDecision -->|Minimum met| SourceQuality["DuckDB source quality checks"]
    SourceQuality -->|Fatal quality failure| FailedRun
    SourceQuality -->|Pass or warning| PublicationCities["Write explicit publication_cities.parquet"]

    PublicationCities --> Staging["data/processed/.staging-run_id"]
    RuleParquet --> Marts
    MemberParquet --> Marts
    RawSnapshot --> Marts["DuckDB SQL Mart Build"]
    HistoryParquet --> Marts
    Marts --> Baselines["historical_baselines.parquet"]
    Marts --> Conditions["city_conditions.parquet"]
    Marts --> Triggers["active_triggers.parquet"]
    Marts --> Outreach["outreach_queue.parquet"]
    Marts --> Alerts["stakeholder_alerts.parquet"]
    SourceQuality --> QualityResults["quality_results.parquet"]
    Baselines --> Staging
    Conditions --> Staging
    Triggers --> Staging
    Outreach --> Staging
    Alerts --> Staging
    QualityResults --> Staging

    Staging --> Contract["Publication contract: required datasets, consent, uniqueness, persistence"]
    Contract -->|Failure| FailedRun
    Contract -->|Pass| AtomicPublish["Atomic directory rename to data/processed/run_id"]
    AtomicPublish --> Lineage["Record published_datasets lineage"]
    AtomicPublish --> AdvanceWatermarks["Advance only successful source-city watermarks"]
    AdvanceWatermarks --> CompleteRun["Mark success or partial_success"]
    CompleteRun --> Retention["Keep five newest forecast and processed snapshots"]

    SQLiteDB[("data/metadata/pipeline.db")] --> DashboardRead["app.py selects latest published run"]
    CompleteRun --> SQLiteDB
    Quarantine --> SQLiteDB
    Lineage --> SQLiteDB
    AtomicPublish --> PublishedMarts[("Published Parquet Marts")]
    PublishedMarts --> DashboardRead
    DashboardRead --> Dashboard["Streamlit care-operations and pipeline-health dashboard"]
```

## Current Data Contracts

| Layer | Dataset or state | Natural key or version boundary |
|---|---|---|
| Forecast raw | Weather and air-quality city snapshots | `source + city_id + observed_at`, partitioned by `run_id` |
| Historical raw | NASA POWER daily records | `city_id + observed_date`, partitioned by baseline year, city, and year |
| Regional rule reference | Definitions, predicates, and relevant conditions | Deterministic `ruleset_version` |
| Synthetic member reference | Members and member conditions | Deterministic generator and city-set version |
| Publication scope | Complete cities eligible for a run | `run_id + city_id` |
| Active trigger | Sustained rule breach | `ruleset_version + rule_id + city_id + window_start` |
| Outreach queue | Consent-aware member-rule action | `member_id + rule_id + window_start` |
| Operational state | Runs, readiness, watermarks, rejects, and lineage | SQLite-managed keys defined in migrations |

## Component Review Sequence

We will review and optimize components in this order because each stage defines the contract required by the
next stage:

1. **Configuration and domain model**: supported cities, scenario catalog, thresholds, persistence windows,
   publication policy, and correction lookback.
2. **API clients and schema validation**: concurrency, retries, timeouts, response parsing, validation, and
   source-specific failure handling.
3. **Incremental raw storage**: watermark semantics, correction overlap, deduplication, snapshot merge,
   partitioning, compression, and retention.
4. **Historical baselines**: cache lifecycle, baseline periods, percentile methodology, and refresh strategy.
5. **Quality, readiness, and quarantine**: source checks, invalid records, success and partial-success policy,
   and publication eligibility.
6. **Regional rule engine**: compiled rule model, compound predicates, historical thresholds, and persistence
   evaluation.
7. **Care-operations marts**: city conditions, triggers, consent-aware outreach, stakeholder aggregation, and
   product usefulness.
8. **Publication and metadata**: staging, atomic publication, lineage, watermarks, migrations, and failure
   semantics.
9. **Dashboard read layer**: current SQL access pattern and existing KPIs. Full KPI and design redesign happens
   only after the preceding components are finalized.
10. **Later operational phase**: scheduling, recovery, monitoring, notifications, and expanded runbook
    documentation.

## Current Boundaries

### Implemented

- Manual end-to-end ETL execution
- Async API calls with retries, timeouts, and bounded concurrency
- Schema validation and source-city failure quarantine
- Watermark-driven incremental forecast snapshots
- Parquet and DuckDB analytical processing
- Config-driven regional and compound rules
- Historical percentile baselines
- Quality and readiness gates with partial publication
- Atomic publication, lineage, retention, and SQLite operational metadata
- Streamlit dashboard for product outputs and pipeline health

### Deliberately Deferred

- Installed scheduler and overlap locking
- Automatic abandoned-run recovery and backfill commands
- External monitoring, alert routing, and notifications
- Dashboard KPI and visual redesign
- Full operational runbook and deployment architecture
