# AI Usage And Human Review

AI-assisted development was used throughout the assignment as an engineering collaborator, not as an
unreviewed code generator.

## How AI Was Used

- Interpreted the assignment and compared possible public-data product directions.
- Researched keyless public APIs and India-specific environmental scenarios.
- Proposed architecture, data models, quality checks, analytical marts, and dashboard metrics.
- Implemented and refactored Python, SQL, configuration, tests, and documentation.
- Diagnosed failures, reviewed repository structure, consolidated files, and ran regressions.
- Explained components and trade-offs during iterative design reviews.

## Human Decisions And Challenges

The user actively changed or rejected AI suggestions:

- Required a digital-therapeutics use case rather than a generic environmental dashboard.
- Required synthetic members because real health data is sensitive and unavailable.
- Expanded the product from seasonal alerts to year-round, region-specific scenarios.
- Required historical local baselines instead of relying only on fixed thresholds.
- Required Parquet and DuckDB for analytics instead of SQLite staging.
- Required SQL ownership under `sql/`, repository cleanup, and repeated regression testing.

## Review And Verification

AI-generated changes were checked through:

- Pydantic configuration and source-contract validation
- Rule conflict review
- Unit and integration tests
- SQL artifact existence and rendering tests
- Fresh and upgraded SQLite schema tests
- Live API-backed ETL executions
- Dashboard query and usability reviews
- `git diff --check` and repository-wide stale-reference searches

The chronological decision trail is recorded in [`../ai_transcript/transcript.md`](../ai_transcript/transcript.md).
