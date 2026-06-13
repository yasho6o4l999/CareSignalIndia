# Reference Data Layer

The reference layer separates mutable operational member state from immutable analytical inputs.

## Member Lifecycle

1. A fixed seed, city weights, member count, and configured `anchor_date` deterministically generate the
   synthetic member source.
2. SQLite transactionally replaces `dim_member` and `bridge_member_condition`, enforcing keys and accepted
   values.
3. The pipeline reads the current member state back from SQLite.
4. A city-partitioned Parquet snapshot is written under a staging directory.
5. The snapshot manifest validates checksums, schemas, row counts, unique member IDs, and condition
   referential integrity.
6. The staging directory is atomically renamed to `snapshot_id=<member-version>`.
7. SQLite registers the manifest and every pipeline run records its `member_snapshot_id`.

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

## Current Boundary

The prototype performs a deterministic full refresh of the synthetic operational dimensions because there is
no external member change feed. A production implementation should ingest incremental changes, retain
effective-dated member history, separate frequently changing outreach activity, and rebuild only affected
city snapshot partitions.
