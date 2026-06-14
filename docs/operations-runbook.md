# Operations Runbook

## Normal Run

```bash
./scripts/run_etl.sh
```

The ETL obtains `data/metadata/etl.lock` before execution. A second overlapping invocation exits immediately
without creating a run. Every successful or failed run records component duration, input rows, output rows,
status, and error context in SQLite `pipeline_stage_execution`.

## Failure Recovery

1. Inspect the latest run, source readiness, validation issues, quality results, and component metrics in the
   dashboard Pipeline Health section.
2. Retry failed source-city calls diagnostically:

```bash
python -m src.retry_failed_sources --run-id <failed-run-id>
```

The diagnostic retry validates whether sources recovered but deliberately does not write raw data, advance
watermarks, or publish a partial result. When targets recover, rerun the normal idempotent ETL command.

3. A normal rerun reads the last successful source-city watermarks, reuses unchanged forecast content,
   removes abandoned raw staging directories, and publishes only after readiness and quality gates pass.

## Monitoring Signals

- Source-city status, attempts, HTTP status, latency, response bytes, freshness, and incremental changes
- Component duration and row flow
- Validation issues and invalid-record counts
- Source, reconciliation, anomaly, and cross-mart quality outcomes
- At-risk, contactable, high-priority, lifecycle, and outreach-gap workload

Recommended production alerts include mandatory-city failure, freshness breach, quality failure, invalid-volume
spike, abnormal workload change, and component duration above its service-level objective.

## Safety

- Failed runs never replace the latest published dashboard run.
- Diagnostic retries never advance watermarks.
- Atomic publication prevents the dashboard from reading partial marts.
- Generated data, metadata, analytical history, and credentials are excluded from Git.
