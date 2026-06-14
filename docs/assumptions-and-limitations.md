# Assumptions And Limitations

## Product Assumptions

- Environmental conditions can inform care-operations review but do not establish individual clinical risk.
- Synthetic members are sufficient to demonstrate joins, segmentation, consent-aware prioritization, and
  workload estimation without using sensitive health data.
- City is the assignment's location grain; neighborhood and exact-location variation are not modeled.
- Chronic-condition relevance profiles and thresholds are prototype business rules requiring clinical and
  operational review before production use.
- Outreach consent is used only to describe a consented review subset. The system sends no messages and
  stores no completed-contact history.

## Data Assumptions

- Open-Meteo forecasts are revision-prone rolling snapshots, so each run re-fetches the available horizon and
  compares it with the previous successful snapshot.
- Open-Meteo air quality is modeled forecast data, not ground-station observation.
- NASA POWER provides an appropriate historical reference for demonstrating city-month percentiles.
- Historical baselines use the previous five complete calendar years and refresh when a new complete year is
  available.
- Historical dashboard dates represent retained forecast snapshots, not observed environmental outcomes.

## Operational Limitations

- The installed workflow is local and single-node.
- The included cron entry is an example and is not installed automatically.
- External monitoring, notifications, authentication, and role-based access are not implemented.
- The synthetic member source emits a deterministic full extract; SQLite reconciles it incrementally.
- Analytical marts are immutable per run and rebuilt because the assignment scale is small.
- Data retention is local filesystem retention, not regulated archival or deletion management.

## Safety And Privacy Boundary

- No real member, medical, contact, or location-identifying data is used.
- Synthetic members contain no names, phone numbers, email addresses, exact addresses, or real identifiers.
- Priority scores are operational review priorities, not medical advice or clinical risk scores.
- Production use would require clinical governance, privacy review, security controls, consent enforcement,
  access auditing, and approved member-engagement workflows.
