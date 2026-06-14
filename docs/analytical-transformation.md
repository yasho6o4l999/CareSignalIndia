# Analytical Transformation Layer

The analytical layer separates environmental exposure from care-team actionability. DuckDB builds immutable
Parquet marts directly from validated source and reference datasets without loading full datasets into pandas.

## Daily Fact Contracts

| Dataset | Grain | Primary purpose |
|---|---|---|
| `environmental_conditions_daily` | Decision date, city, rule | Ticker conditions and active environmental context |
| `environmental_metrics_daily` | Decision date, city, metric | Forecast minimum, average, maximum, and local historical comparison |
| `member_risk_exposure_daily` | Decision date, member, city, rule | Potentially at-risk population with consent-aware review attributes |
| `care_workload_daily` | Decision date, city | Dashboard KPIs and city comparison |

`member_risk_exposure_daily` deliberately includes members without outreach consent. It records
`outreach_eligible` and an ineligibility reason. The prioritization queue is a governed subset containing only
consented exposure rows; it represents potential workload, not completed outreach.

## KPI Definitions

- **Potentially at-risk members:** distinct active members with a relevant condition in a city with an active
  environmental condition on the selected date.
- **At-risk percentage:** potentially at-risk members divided by total active members in publication-approved
  cities included by the dashboard filter.
- **Consented at-risk members:** at-risk members with outreach consent.
- **High-priority members:** at-risk members with a priority score of four or higher.
- **Affected cities:** cities with at least one potentially at-risk member.

## Care Operations Insights

The dashboard converts the daily facts into operational questions:

- **Highest-burden city:** where the largest potentially at-risk cohort requires review.
- **Largest consent gap:** where the most at-risk members have not provided outreach consent.
- **Dominant risk driver:** which environmental condition affects the largest distinct-member cohort.
- **Consent readiness by city:** consented workload compared with the current consent gap.
- **Vulnerable cohort workload:** consented and high-priority demand by chronic condition.
- **Recommended contact-channel demand:** expected workload by members' preferred outreach channel.

## Historical Serving

After a successful run passes quality gates, the pipeline publishes the four lightweight daily facts under
`data/analytical_history/run_id=<run_id>/`. Local files use hard links when possible, so processed-run retention
can remove its directory without deleting retained history or duplicating file contents.

The dashboard maps each available decision date to the latest successful retained snapshot containing it.
Changing the dashboard date only changes DuckDB reads; it does not rerun ETL or call an API. The default
retention is configured as 90 days in `config/runtime.yml`.
