# Analytical Transformation Layer

The analytical layer separates environmental exposure from care-team actionability. DuckDB builds immutable
Parquet marts directly from validated source and reference datasets without loading full datasets into pandas.

## Daily Fact Contracts

| Dataset | Grain | Primary purpose |
|---|---|---|
| `environmental_conditions_daily` | Decision date, city, rule | Ticker conditions and active environmental context |
| `environmental_metrics_daily` | Decision date, city, metric | Forecast minimum, average, maximum, and local historical comparison |
| `member_risk_exposure_daily` | Decision date, member, city, rule | Potentially at-risk population before outreach policy filters |
| `care_workload_daily` | Decision date, city | Dashboard KPIs and city comparison |

`member_risk_exposure_daily` deliberately includes members without outreach consent and members inside the
contact cooldown. It records `outreach_eligible` and an ineligibility reason. The outreach queue is a governed
subset containing only eligible exposure rows.

## KPI Definitions

- **Potentially at-risk members:** distinct active members with a relevant condition in a city with an active
  environmental condition on the selected date.
- **At-risk percentage:** potentially at-risk members divided by total active members in publication-approved
  cities included by the dashboard filter.
- **Contactable at-risk members:** at-risk members satisfying consent and cooldown policies.
- **High-priority members:** at-risk members with a priority score of four or higher.
- **Affected cities:** cities with at least one potentially at-risk member.

## Care Operations Insights

The dashboard converts the daily facts into operational questions:

- **Highest-burden city:** where the largest potentially at-risk cohort requires review.
- **Largest outreach gap:** where consent or cooldown prevents contact with the most at-risk members.
- **Dominant risk driver:** which environmental condition affects the largest distinct-member cohort.
- **Outreach readiness by city:** contactable workload compared with the current outreach gap.
- **Vulnerable cohort workload:** contactable and high-priority demand by chronic condition.
- **Recommended contact-channel demand:** expected workload by members' preferred outreach channel.

## Historical Serving

After a successful run passes quality gates, the pipeline publishes the four lightweight daily facts under
`data/analytical_history/run_id=<run_id>/`. Local files use hard links when possible, so processed-run retention
can remove its directory without deleting retained history or duplicating file contents.

The dashboard maps each available decision date to the latest successful retained snapshot containing it.
Changing the dashboard date only changes DuckDB reads; it does not rerun ETL or call an API. The default
retention is configured as 90 days in `config/runtime.yml`.
