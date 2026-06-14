# Reference Data Layer

The reference layer separates mutable operational member state from immutable analytical inputs.

## Member Lifecycle

1. A fixed seed, city weights, member count, and configured `anchor_date` deterministically generate the
   synthetic member source.
2. SQLite incrementally reconciles `dim_member` and `bridge_member_condition`, enforcing keys and accepted
   values while recording inserted, updated, deactivated, unchanged, and condition-change counts.
3. The pipeline reads the current member state back from SQLite.
4. Durable member changes create SCD Type 2 records in `dim_member_history`. Contact events are recorded
   separately in `member_outreach_activity` and do not create unnecessary dimension versions.
5. A content-addressed, city-partitioned Parquet snapshot is written under a staging directory. Unchanged
   city partitions are copied from the previous validated snapshot.
6. The snapshot manifest validates checksums, schemas, row counts, unique member IDs, and condition
   referential integrity.
7. The staging directory is atomically renamed to `snapshot_id=<member-version>-<content-hash>`.
8. SQLite registers the manifest and every pipeline run records its `member_snapshot_id`.

```text
data/reference/member_snapshots/
  snapshot_id=<version>/
    manifest.json
    members/city_id=<city>/data.parquet
    member_conditions/city_id=<city>/data.parquet
```

SQLite is used for transactional operational state and constraints. DuckDB reads the partitioned Parquet
snapshot so analytical joins retain column pruning, predicate pushdown, compression, and reproducible input
versions.

## Snapshot Manifest

The manifest records snapshot and configuration versions, creation timestamp, schema version, total row
counts, and per-file paths, row counts, sizes, schemas, and SHA-256 checksums. A cached snapshot is reused
only after manifest integrity verification succeeds.

## Retention

Member snapshot retention preserves every snapshot referenced by a successful or partial-success pipeline
run. It also keeps the configured number of newest recovery snapshots and removes only older unreferenced
versions.

## Current Boundary

The synthetic generator still emits a complete deterministic source extract because there is no external
member change feed. The operational layer reconciles that extract incrementally. A production implementation
would consume source-native changes and apply the same reconciliation contract.
