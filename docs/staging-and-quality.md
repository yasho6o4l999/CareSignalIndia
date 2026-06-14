# Staging And Quality

Component 8 protects the boundary between validated source snapshots and atomically published analytical
products. Its thresholds live in `config/quality_policy.yml`; Python coordinates checks and persists results,
while executable profiling and reconciliation logic lives under `sql/quality/`.

## Quality Gates

| Gate | Checks | Publication behavior |
|---|---|---|
| Source profile | Non-empty, minimum forecast coverage, unique natural keys, and freshness | Any failure blocks mart construction |
| Historical profile | Expected city, year, and row coverage | Any failure blocks mart construction |
| Cross-source reconciliation | Weather and air-quality forecast-hour join loss for publication-approved cities | Configured warning is visible; configured failure blocks mart construction |
| Historical anomaly | Current source row count compared with the average of prior successful-run profiles | Configured warning or failure severity |
| Cross-mart integrity | Consent leakage, duplicate outreach, invalid persistence, orphan outreach, alert and workload reconciliation, risk-exposure lineage, and publication-city scope | Any count above its configured maximum blocks publication |

## Historical Profiles

Each run stores numeric evidence in SQLite `quality_profile`, keyed by run, stage, dataset, and metric. The
anomaly baseline uses prior `success` and `partial_success` runs only. Until the configured minimum history
exists, the anomaly check passes with `baseline=insufficient` in its details rather than inventing a baseline.

## Reconciliation Scope

Cross-source reconciliation considers future forecast hours for cities that passed publication readiness.
Weather-side and air-quality-side loss are measured separately because the APIs can expose different forecast
horizons. Cross-mart checks then treat the staged marts as one product contract and reconcile member-level
outreach back to triggers and stakeholder aggregates before atomic publication.
