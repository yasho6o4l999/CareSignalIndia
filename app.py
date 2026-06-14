from pathlib import Path

import duckdb
import streamlit as st

from src.config import load_cities
from src.metadata import DATABASE_PATH, MetadataStore
from src.sql import render_sql


ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="CareSignal India", layout="wide")
st.title("CareSignal India")
st.caption("Year-round environmental care-operations intelligence using synthetic member data.")

if not DATABASE_PATH.exists():
    st.info("No processed data found. Run `python etl.py` first.")
    st.stop()

metadata = MetadataStore()
latest_run = metadata.latest_published_run()
if latest_run is None:
    st.info("No successfully published run found. Run `python etl.py` first.")
    st.stop()

run_id = latest_run["run_id"]
run_root = ROOT / f"data/processed/run_id={run_id}"
connection = duckdb.connect()

alerts_sql = render_sql(
    "dashboard/stakeholder_alerts.sql",
    stakeholder_alerts_path=run_root / "stakeholder_alerts.parquet",
)
queue_count_sql = render_sql(
    "dashboard/outreach_member_count.sql",
    outreach_queue_path=run_root / "outreach_queue.parquet",
)
today_alerts = connection.execute(alerts_sql, ["today_action"]).fetch_arrow_table()
upcoming_alerts = connection.execute(alerts_sql, ["upcoming_risk"]).fetch_arrow_table()
today_queue_count = connection.execute(queue_count_sql, ["today_action"]).fetchone()[0]
upcoming_queue_count = connection.execute(queue_count_sql, ["upcoming_risk"]).fetchone()[0]
quality_failures = connection.execute(
    render_sql(
        "dashboard/quality_issue_count.sql",
        quality_results_path=run_root / "quality_results.parquet",
    )
).fetchone()[0]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Members requiring action today", today_queue_count)
col2.metric("Today's stakeholder alerts", today_alerts.num_rows)
col3.metric("Upcoming risks", upcoming_alerts.num_rows)
col4.metric("Quality warnings/failures", quality_failures)

st.caption(
    f"Published run `{run_id}` · status `{latest_run['status']}` · "
    f"ruleset `{latest_run['ruleset_version']}` · member snapshot `{latest_run['member_snapshot_id']}` · "
    f"baseline through `{latest_run['baseline_end_year']}`"
)

city = st.selectbox("City", ["All", *[city.city_id for city in load_cities()]])
selected_city = None if city == "All" else city
queue_sql = render_sql(
    "dashboard/outreach_queue.sql",
    outreach_queue_path=run_root / "outreach_queue.parquet",
)

st.header("Today's Actions")
st.caption("Forecast events beginning today that require immediate care-operations review.")
st.subheader("Today's stakeholder alerts")
st.dataframe(today_alerts, width="stretch")
st.subheader("Today's member outreach queue")
today_queue = connection.execute(
    queue_sql, ["today_action", selected_city, selected_city]
).fetch_arrow_table()
st.dataframe(today_queue, width="stretch")

st.header("Upcoming Risks")
st.caption("Qualifying forecast events beginning after today, shown for workload and outreach planning.")
st.subheader("Upcoming stakeholder alerts")
st.dataframe(upcoming_alerts, width="stretch")
st.subheader("Upcoming member outreach queue")
upcoming_queue = connection.execute(
    queue_sql, ["upcoming_risk", selected_city, selected_city]
).fetch_arrow_table()
st.dataframe(upcoming_queue, width="stretch")

st.subheader("City-specific historical baselines")
baselines = connection.execute(
    render_sql(
        "dashboard/historical_baselines.sql",
        historical_baselines_path=run_root / "historical_baselines.parquet",
    ),
    [selected_city, selected_city],
).fetch_arrow_table()
st.dataframe(baselines, width="stretch")

st.subheader("Pipeline health")
recent_runs = metadata.query("queries/recent_runs.sql", (10,))
source_readiness = metadata.query("queries/latest_source_readiness.sql", (run_id,))
invalid_counts = metadata.query("queries/latest_invalid_counts.sql", (run_id,))
validation_issues = metadata.query("queries/latest_validation_issues.sql", (run_id, 100))
operational_quality = metadata.query("queries/latest_quality_results.sql", (run_id,))
latest_inserted = sum(row["records_inserted"] for row in source_readiness)
latest_updated = sum(row["records_updated"] for row in source_readiness)
latest_unchanged = sum(row["records_unchanged"] for row in source_readiness)
latest_rejected = sum(row["records_rejected"] for row in source_readiness)
metric_columns = st.columns(4)
metric_columns[0].metric("Inserted", latest_inserted)
metric_columns[1].metric("Updated", latest_updated)
metric_columns[2].metric("Unchanged", latest_unchanged)
metric_columns[3].metric("Rejected", latest_rejected)
failed_sources = [dict(row) for row in source_readiness if row["status"] == "failed"]
if latest_run["status"] == "partial_success":
    unavailable = sorted({row["city_id"] for row in failed_sources})
    st.warning(
        f"This is a partial publication. Unavailable cities: {', '.join(unavailable)}. "
        "Their previous successful watermarks were preserved."
    )
st.dataframe([dict(row) for row in recent_runs], width="stretch")
st.dataframe([dict(row) for row in source_readiness], width="stretch")
if invalid_counts:
    st.dataframe([dict(row) for row in invalid_counts], width="stretch")
if validation_issues:
    st.caption("Latest field-level validation issues")
    st.dataframe([dict(row) for row in validation_issues], width="stretch")
if operational_quality:
    st.caption("Persisted operational quality checks")
    st.dataframe([dict(row) for row in operational_quality], width="stretch")

st.warning("Synthetic demonstration data only. This product does not provide medical advice or clinical risk scores.")
metadata.close()
