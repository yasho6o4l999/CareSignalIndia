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

SQLite `extraction_metrics` records request duration, attempts, HTTP status, response bytes, and final HTTP
status per source and city.

## Raw Publication

Forecast records are merged under `data/raw/.staging/` before atomic publication to the run directory. Each
source-city Parquet file receives a JSON sidecar manifest with:

- Semantic content hash excluding volatile extraction and run metadata
- Physical file SHA-256 checksum
- Row count and timestamp range
- Source, city, and run identifiers
- Prior run reused, when applicable

After the incremental merge, the semantic hash is compared with the previous successful source-city
snapshot. Identical content is hard-linked where supported, avoiding duplicate storage while preserving a
complete immutable run layout. SQLite `raw_manifests` provides queryable lineage for every raw artifact.

## Current Boundary

Open-Meteo exposes a revision-prone rolling forecast rather than a source change feed, so the pipeline still
retrieves the forecast window before comparing it. Production storage should additionally apply
lineage-aware raw retention and landing-zone retention for original source payloads.
