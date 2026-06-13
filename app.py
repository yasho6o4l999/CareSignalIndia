import json
from pathlib import Path

import duckdb
import streamlit as st

from src.sql import render_sql


ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="CareSignal India", layout="wide")
st.title("CareSignal India")
st.caption("Year-round environmental care-operations intelligence using synthetic member data.")

latest_path = ROOT / "data/processed/latest_run.json"
if not latest_path.exists():
    st.info("No processed data found. Run `python etl.py` first.")
    st.stop()

run_id = json.loads(latest_path.read_text(encoding="utf-8"))["run_id"]
run_root = ROOT / f"data/processed/run_id={run_id}"
connection = duckdb.connect()

alerts = connection.execute(
    render_sql(
        "dashboard/stakeholder_alerts.sql",
        stakeholder_alerts_path=run_root / "stakeholder_alerts.parquet",
    )
).fetch_arrow_table()

queue_count = connection.execute(
    render_sql(
        "dashboard/outreach_member_count.sql",
        outreach_queue_path=run_root / "outreach_queue.parquet",
    )
).fetchone()[0]
quality_failures = connection.execute(
    render_sql(
        "dashboard/quality_issue_count.sql",
        quality_results_path=run_root / "quality_results.parquet",
    )
).fetchone()[0]

col1, col2, col3 = st.columns(3)
col1.metric("Eligible members", queue_count)
col2.metric("Active stakeholder alerts", alerts.num_rows)
col3.metric("Quality warnings/failures", quality_failures)

st.subheader("Stakeholder alerts")
st.dataframe(alerts, width="stretch")

st.subheader("Member outreach queue")
city = st.selectbox("City", ["All", "delhi", "mumbai", "bengaluru", "chennai", "ahmedabad"])
selected_city = None if city == "All" else city
queue = connection.execute(
    render_sql(
        "dashboard/outreach_queue.sql",
        outreach_queue_path=run_root / "outreach_queue.parquet",
    ),
    [selected_city, selected_city],
).fetch_arrow_table()
st.dataframe(queue, width="stretch")

st.warning("Synthetic demonstration data only. This product does not provide medical advice or clinical risk scores.")
