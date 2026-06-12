# CareSignal India

CareSignal India is a year-round environmental care-intelligence prototype for digital therapeutics care-operations teams. It combines public environmental forecasts with deterministic synthetic chronic-care member data to create explainable, consent-aware outreach queues.

The initial vertical slice supports Delhi, Mumbai, Bengaluru, Chennai, and Ahmedabad. It models heat, cold, heavy-rain, and particulate-pollution triggers, including a Delhi winter-pollution rule.

## Architecture

- Bounded asynchronous API extraction with connection pooling, timeouts, and retries
- Pydantic schema and accepted-range validation
- Partitioned, ZSTD-compressed Parquet storage
- DuckDB transformations directly over Parquet
- Predicate pushdown in dashboard queries
- Deterministic synthetic members with consent controls
- Machine-readable freshness, uniqueness, and non-empty quality checks

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

Open-Meteo's free endpoint is intended for non-commercial use. This repository is an educational candidate assignment.

## Data Model

Raw datasets are partitioned by `source` and `run_id`. DuckDB builds:

- `city_conditions.parquet`
- `outreach_queue.parquet`
- `stakeholder_alerts.parquet`
- `quality_results.parquet`

Synthetic member data contains no names, contact details, exact addresses, or real identifiers. Outreach priority is an operational demonstration, not a clinical risk score.

## Scheduling

The required reviewer workflow is manual. `deployment/crontab.example` demonstrates a six-hour production-style refresh schedule. A real deployment should additionally use an overlap lock, managed secrets, monitoring, and alerting.

## Current Limitations

- This initial version uses fixed transparent thresholds rather than city-specific historical percentiles.
- Regional rules are validated but the first SQL mart contains a simplified equivalent rule implementation.
- Open-Meteo provides modeled air-quality forecasts rather than ground-station observations.
- No messages are sent; the project only generates stakeholder and outreach queues.
- The scheduler example is not installed automatically.

## Next Improvements

- Add NASA POWER historical baselines and city-specific anomaly detection
- Compile YAML regional rules into DuckDB evaluation tables
- Add quarantined-record outputs and partial-source publication
- Add extraction manifests and incremental retention policies
- Add mocked API integration tests and query-plan benchmarks
