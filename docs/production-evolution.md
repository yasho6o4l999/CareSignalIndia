# Production Evolution

## Analytical Incrementality

The assignment keeps immutable per-run marts because seven cities and 5,000 synthetic members rebuild quickly
and provide simple recovery semantics. At larger scale, source change metrics should identify affected
city-date partitions so conditions, triggers, exposure, and workload facts can be rebuilt selectively.
Historical baselines should refresh only when a complete year or supported-city set changes.

## Forecast Effectiveness

A production system should ingest observed environmental outcomes and compare them with retained forecasts.
This enables forecast error, trigger precision, false-positive rate, and rule-effectiveness monitoring.

## Privacy And Access

Real member integration should use tokenized identifiers, encryption, least-privilege roles, member-detail
access auditing, retention and deletion policies, and strict separation between operational outreach support
and clinical recommendations. Aggregate dashboard users should not automatically receive member-level access.

## Contract Governance

Source, mart, quality-policy, KPI, and dashboard contracts should have explicit versions and compatibility
checks. Breaking schema or KPI-definition changes should require impact analysis and reviewer approval.
