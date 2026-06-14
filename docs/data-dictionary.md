# Data Dictionary

## Source And Reference Data

| Dataset | Grain | Important fields | Purpose |
|---|---|---|---|
| Weather raw snapshot | Source, city, forecast hour | temperature, apparent temperature, precipitation, humidity, wind | Forecast environmental conditions |
| Air-quality raw snapshot | Source, city, forecast hour | PM2.5, PM10 | Forecast pollution conditions |
| NASA POWER history | City, observed date | daily minimum, maximum, range, precipitation | Local historical baselines |
| `dim_member` | Synthetic member | city, age band, language, preferred channel, consent, active flag | Transactional current member state |
| `bridge_member_condition` | Member, chronic condition | member ID, condition | Many-to-many member conditions |
| Compiled regional rules | Ruleset version, rule components | applicability, predicates, condition relevance, severity bands | Reproducible rule evaluation |

## Published Analytical Data

| Dataset | Grain | Purpose |
|---|---|---|
| `historical_baselines.parquet` | City, month, metric | City-month p10, p90, and p95 reference values |
| `city_conditions.parquet` | City, forecast hour | Joined and derived environmental metrics |
| `active_triggers.parquet` | City, rule, persistence window | Sustained rule breaches and timing classification |
| `environmental_conditions_daily.parquet` | Decision date, city, rule | Dashboard environmental context |
| `environmental_metrics_daily.parquet` | Decision date, city, metric | Forecast summaries and local historical comparison |
| `member_risk_exposure_daily.parquet` | Decision date, member, city, rule | Potentially affected members and review priority |
| `care_workload_daily.parquet` | Decision date, city | Total, at-risk, consented, and high-priority workload |
| `outreach_queue.parquet` | Member, rule, trigger window | Legacy internal name for the consented prioritization subset |
| `stakeholder_alerts.parquet` | Trigger and timing segment | Legacy internal name for aggregated review workload |
| `quality_results.parquet` | Run, quality check, dataset | Published quality outcomes |

## Operational Metadata

| Domain | Tables | Purpose |
|---|---|---|
| Runs | `operational_run`, `operational_run_metric` | Run status, versions, counts, and publication state |
| Stages | `pipeline_stage_execution` | Stage timing, row flow, and errors |
| Source state | `extraction_request_metric`, `source_pipeline_state` | API evidence, readiness, changes, failures, and watermarks |
| Quality | `quality_check_result`, `quality_profile`, `validation_issue` | Quality outcomes, anomaly history, and invalid-record evidence |
| Lineage | `data_artifact`, `artifact_dependency` | Artifact metadata and derivation relationships |
| References | `reference_snapshot`, `reference_sync_run` | Member snapshot registry and reconciliation metrics |

## Important Semantic Fields

| Field | Meaning |
|---|---|
| `decision_date` | Local dashboard date in `Asia/Kolkata` |
| `action_timing` | `today_action` or `upcoming_risk`; timing classification only, not proof of an action |
| `outreach_consent` | Synthetic governance attribute indicating consent |
| `outreach_eligible` | Legacy field name meaning the at-risk row has outreach consent |
| `priority_score` | Prototype operational review priority, not a clinical risk score |
| `configuration_version` | Deterministic hash of active configuration |
| `ruleset_version` | Deterministic hash of compiled regional rules |
| `member_snapshot_id` | Content-addressed member analytical snapshot identifier |
