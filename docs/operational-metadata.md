# Operational Metadata Control Plane

SQLite is the transactional control plane for pipeline execution, recovery, lineage, and monitoring. The
repository now creates only the normalized schema; operational facts have one authoritative write path.

## Normalized Domains

| Domain | Tables | Responsibility |
|---|---|---|
| Run execution | `operational_run`, `operational_run_metric` | Immutable run context separated from mutable counters |
| Component execution | `pipeline_stage_execution` | Stage duration, input/output rows, status, and failure context |
| Source execution and state | `extraction_request_metric`, `source_pipeline_state` | Request evidence captured before readiness, then one historical source-city state containing readiness, incremental changes, errors, and resulting watermark |
| Artifact lineage | `data_artifact`, `artifact_dependency` | Unified raw, compacted, reference, and processed artifact metadata plus `reused_from`, `compacted_from`, and `derived_from` relationships |
| Data quality | `quality_check_result`, `quality_profile`, `validation_issue` | Queryable outcomes, historical metric profiles, and structured record-level evidence |
| Reference operations | `reference_snapshot`, `reference_sync_run` | Consistent registry for governed reference snapshots and sync execution |

## Source State Semantics

`source_pipeline_state` intentionally combines source operations and state management. It preserves every
source-city execution while storing the previous and resulting watermark on the same row. The
`current_source_state` view exposes the latest successful watermark without requiring a separate mutable
watermark table. `latest_run_source_health` exposes the most recent execution health.

Successful run completion and all source watermark advances occur in one SQLite transaction. A failed
transaction therefore cannot publish a successful run while leaving its source states behind.

Application access is separated into focused `RunRepository`, `SourceStateRepository`, `ArtifactRepository`,
`QualityRepository`, and `MemberRepository` responsibilities. `MetadataStore` coordinates their transactions.

SQLite writes are grouped into two named-statement bundles under `sql/sqlite/mutations/`:
`insert_statements.sql` contains inserts and upserts, while `update_statements.sql` contains updates and
deletes. Callers resolve one named section at a time, preserving parameterized execution without maintaining
a separate file for every small statement. SQLite reads follow the same convention in
`sql/sqlite/queries/query_statements.sql`.

## Artifact Lineage

Every persisted file receives a deterministic artifact ID:

- Raw city and compacted snapshots: `raw:<run>:<source>:<city>`
- Processed marts: `processed:<run>:<dataset>`
- Member references: `reference:member:<snapshot>`

Dependencies provide end-to-end traceability:

- `reused_from`: unchanged content reused from a previous run
- `compacted_from`: source-level compacted artifact derived from city snapshots
- `derived_from`: processed artifact derived from compacted forecasts and the run's member snapshot

## Migration Boundary

The take-home repository has no deployed consumer history, so its migration chain is intentionally concise:
`001_control_plane_schema.sql` defines the final tables and `002_indexes_and_views.sql` defines access paths.
`003_remove_outreach_execution_state.sql` demonstrates a backward-compatible upgrade that preserves members
and condition mappings while removing obsolete contact-history state. The migration registry remains in place
to support deterministic future upgrades.

## Database Health

Sessions enforce foreign keys, WAL mode, a five-second busy timeout, normal synchronous durability, and
incremental vacuum support. After successful retention, the pipeline runs controlled `PRAGMA optimize`,
incremental vacuum, and a passive WAL checkpoint. Composite indexes target latest-source-state, run-health,
lineage, validation, and quality-monitoring queries. Detailed control-plane history is retained because it is
small and audit-critical; large generated files continue to follow the separate raw and processed retention
policies.

`quality_profile` stores numeric observations such as source row counts, forecast join-loss ratios, and
cross-mart exception counts. Anomaly checks compare the current run only with profiles from prior successful
or partial-success runs, so failed or incomplete executions cannot distort the baseline.
