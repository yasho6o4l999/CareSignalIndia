# API Extraction And Incremental Raw Storage

## Extraction Policies

`config/extraction_policy.yml` defines source-specific concurrency, timeout, retry, minimum-record, and
expected-interval contracts. Open-Meteo weather, Open-Meteo air quality, and NASA POWER therefore retain
independent operational behavior.

The clients:

- Bound concurrent requests with source-specific semaphores.
- Retry only timeouts, network failures, HTTP 429, and HTTP 5xx transient responses.
- Respect `Retry-After` for rate limits and otherwise use exponential backoff with jitter.
- Do not retry permanent HTTP 4xx errors or response-contract failures.
- Validate required response arrays, matching array lengths, minimum records, timestamp order, uniqueness,
  and expected intervals where applicable.

SQLite `extraction_request_metric` records request duration, attempts, HTTP status, response bytes, and final
HTTP status before readiness is known. Those metrics are incorporated into the authoritative
`source_pipeline_state` row when the source-city call succeeds or fails.

## Source Record Validation

Each API response is parsed record by record. Valid records continue through the pipeline while invalid
records are excluded and written to SQLite with their source, city, natural key, field name, original
validation error type, invalid value, payload, severity, and validation-policy version.

`config/extraction_policy.yml` controls the minimum valid-record ratio and maximum invalid-record count per
source. A source-city batch publishes only when it satisfies those thresholds and its minimum valid-record
coverage. This prevents one malformed value from discarding an otherwise useful city response while still
blocking materially degraded datasets.

The air-quality policy permits a bounded number of missing future hours because the API can return a
seven-day timestamp grid with a shorter populated pollution horizon. Those unavailable future values remain
quarantined and visible; the policy does not silently convert them into valid measurements.

Cross-field checks currently enforce historical minimum temperature and calculated temperature range.
PM2.5 above PM10 is retained as a warning because modeled environmental data can contain unusual values that
should be reviewed rather than automatically discarded.

## Raw Publication

Forecast records are merged under `data/raw/.staging/` before atomic publication to the run directory. Each
source-city Parquet file receives a JSON sidecar manifest with:

- Manifest and raw-schema versions plus a deterministic schema fingerprint
- Semantic content hash excluding volatile extraction and run metadata
- Physical file SHA-256 checksum
- File size, row count, row-group count, timestamp range, and column-level statistics
- Source, city, and run identifiers
- Prior run reused, when applicable

The manifest is validated before publication. A schema fingerprint change under the same schema version
blocks publication, requiring an explicit schema-version change instead of allowing an accidental breaking
change into downstream queries.

After the incremental merge, the semantic hash is compared with the previous successful source-city
snapshot. Identical content is hard-linked where supported, avoiding duplicate storage while preserving a
complete immutable run layout. SQLite `data_artifact` provides queryable lineage for every raw artifact.

## Compaction And Recovery

Source-city files remain the incremental retry and lineage boundary. After successful city publications,
the pipeline streams them through PyArrow into one sorted, ZSTD-compressed
`compacted/data.parquet` artifact per source and run. Streaming batches and configured row-group limits
bound memory use. Quality checks and analytical marts prefer these compacted files, reducing each forecast
source from multiple city-file opens to one DuckDB input file.

Compaction behavior is governed by `config/incremental_policy.yml`, including batch size, row-group size,
compression, and whether compaction is enabled. Compacted artifacts receive the same governed manifests and
are registered in SQLite using `city_id=__all__`. When compacted semantic content is unchanged, the new run
hard-links the prior compacted artifact instead of writing a duplicate.

At pipeline startup, abandoned raw staging directories from older runs are removed. The active run's staging
directory is preserved, and all final files and sidecar manifests continue to publish through atomic
renames.

## Current Boundary

Open-Meteo exposes a revision-prone rolling forecast rather than a source change feed, so the pipeline still
retrieves the forecast window before comparing it. Production storage should additionally apply
landing-zone retention for original source payloads.

Generated extracts are intentionally excluded from Git. A reviewer creates them by running `python etl.py`;
the committed `.gitkeep` files preserve the required local directory structure without publishing generated
or potentially sensitive data.
