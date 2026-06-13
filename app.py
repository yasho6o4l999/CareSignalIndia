import json
from pathlib import Path

import duckdb
import streamlit as st


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
    f"""
    SELECT * FROM read_parquet('{run_root / "stakeholder_alerts.parquet"}')
    ORDER BY eligible_members DESC
    """
).fetch_arrow_table()

queue_count = connection.execute(
    f"SELECT count(DISTINCT member_id) FROM read_parquet('{run_root / 'outreach_queue.parquet'}')"
).fetchone()[0]
quality_failures = connection.execute(
    f"SELECT count(*) FROM read_parquet('{run_root / 'quality_results.parquet'}') WHERE status <> 'pass'"
).fetchone()[0]

col1, col2, col3 = st.columns(3)
col1.metric("Eligible members", queue_count)
col2.metric("Active stakeholder alerts", alerts.num_rows)
col3.metric("Quality warnings/failures", quality_failures)

st.subheader("Stakeholder alerts")
st.dataframe(alerts, width="stretch")

st.subheader("Member outreach queue")
city = st.selectbox("City", ["All", "delhi", "mumbai", "bengaluru", "chennai", "ahmedabad"])
predicate = "" if city == "All" else "WHERE city_id = ?"
parameters = [] if city == "All" else [city]
queue = connection.execute(
    f"""
    SELECT member_id, city_id, matched_conditions, rule_id, severity, priority_score,
           preferred_channel, preferred_language, window_start, window_end,
           trigger_explanation
    FROM read_parquet('{run_root / "outreach_queue.parquet"}')
    {predicate}
    ORDER BY priority_score DESC
    LIMIT 500
    """,
    parameters,
).fetch_arrow_table()
st.dataframe(queue, width="stretch")

st.warning("Synthetic demonstration data only. This product does not provide medical advice or clinical risk scores.")
