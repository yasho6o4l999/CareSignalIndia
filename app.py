import html
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import streamlit as st

from src.config import load_cities, load_runtime_settings
from src.metadata import DATABASE_PATH, MetadataStore
from src.sql import render_sql


ROOT = Path(__file__).resolve().parent
HISTORY_ROOT = ROOT / "data/analytical_history"
CARE_WORKLOAD_HISTORY = HISTORY_ROOT / "run_id=*/care_workload_daily.parquet"

st.set_page_config(page_title="CareSignal India", layout="wide")
runtime = load_runtime_settings()
today = datetime.now(ZoneInfo(runtime.decision_timezone)).date()

title_column, date_column = st.columns([4, 1])
title_column.title("CareSignal India")
title_column.caption("Year-round environmental care-operations intelligence using synthetic member data.")
date_column.markdown(
    f"<div style='text-align:right'><b>Today</b><br>{today.strftime('%d %B %Y')}</div>",
    unsafe_allow_html=True,
)

if not DATABASE_PATH.exists() or not HISTORY_ROOT.exists():
    st.info("No analytical history found. Run `python etl.py` first.")
    st.stop()

connection = duckdb.connect()
available = connection.execute(
    render_sql("dashboard/available_dates.sql", care_workload_history_path=CARE_WORKLOAD_HISTORY)
).fetchall()
if not available:
    st.info("No analytical dates are available. Run `python etl.py` first.")
    st.stop()

run_by_date = {row[0]: row[1] for row in available}
available_dates = sorted(run_by_date)
default_date = today if today in run_by_date else available_dates[-1]
selected_date = st.date_input(
    "Analysis date",
    value=default_date,
    min_value=available_dates[0],
    max_value=available_dates[-1],
    help="Refreshes the dashboard from the latest successful analytical snapshot containing this date.",
)
if selected_date not in run_by_date:
    st.warning("No analytical snapshot is available for the selected date.")
    st.stop()

snapshot_run_id = run_by_date[selected_date]
snapshot = HISTORY_ROOT / f"run_id={snapshot_run_id}"
workload_path = snapshot / "care_workload_daily.parquet"
conditions_path = snapshot / "environmental_conditions_daily.parquet"
metrics_path = snapshot / "environmental_metrics_daily.parquet"
member_risk_path = snapshot / "member_risk_exposure_daily.parquet"

city_options = ["All", *[city.city_id for city in load_cities()]]
city = st.selectbox(
    "Dashboard city",
    city_options,
    help="Filters the ticker, KPIs, environmental metrics, member table, and insight charts.",
)
selected_city = None if city == "All" else city

ticker_rows = connection.execute(
    render_sql("dashboard/environmental_ticker.sql", environmental_conditions_path=conditions_path),
    [selected_date, selected_city, selected_city],
).fetchall()
ticker_items = [
    f"{row[0]}: {row[1]} ({row[2]}) · {row[3]} · {row[4]}h"
    for row in ticker_rows
]
ticker_text = "   •   ".join(html.escape(item) for item in ticker_items) or "No active environmental risks"
st.markdown(
    f"""
    <style>
    .ticker {{ overflow: hidden; white-space: nowrap; background: #10263d; color: #f4f8fb;
               padding: 0.7rem; border-radius: 0.5rem; }}
    .ticker span {{ display: inline-block; padding-left: 100%; animation: ticker 35s linear infinite; }}
    .ticker:hover span {{ animation-play-state: paused; }}
    @keyframes ticker {{ 0% {{ transform: translateX(0); }} 100% {{ transform: translateX(-100%); }} }}
    </style>
    <div class="ticker"><span>{ticker_text}</span></div>
    """,
    unsafe_allow_html=True,
)

kpis = connection.execute(
    render_sql("dashboard/executive_kpis.sql", care_workload_path=workload_path),
    [selected_date, selected_city, selected_city],
).fetchone()
total_members, at_risk, at_risk_pct, contactable, high_priority, affected_cities = kpis
kpi_columns = st.columns(5)
kpi_columns[0].metric(
    "Potentially at-risk members",
    f"{at_risk or 0:,}",
    f"{at_risk_pct or 0:.2f}% of {total_members or 0:,}",
    help="Distinct active members whose city, conditions, and selected-date environmental risks match.",
)
kpi_columns[1].metric(
    "Contactable at-risk members",
    f"{contactable or 0:,}",
    help="At-risk members with outreach consent who are outside the configured contact cooldown.",
)
kpi_columns[2].metric(
    "High-priority members",
    f"{high_priority or 0:,}",
    help="Distinct at-risk members with priority score of four or higher.",
)
kpi_columns[3].metric(
    "Affected cities",
    f"{affected_cities or 0:,}",
    help="Publication-approved cities with at least one potentially at-risk member.",
)
kpi_columns[4].metric(
    "Active conditions",
    f"{len(ticker_rows):,}",
    help="Distinct city-level environmental conditions active on the selected date.",
)

st.caption(
    f"Selected date `{selected_date}` · latest matching snapshot `{snapshot_run_id}` · "
    f"history retention `{runtime.analytical_history_retention_days}` days"
)

st.subheader("Relevant Environmental Metrics")
environmental_metrics = connection.execute(
    render_sql(
        "dashboard/environmental_metrics_daily.sql",
        environmental_conditions_path=conditions_path,
        environmental_metrics_path=metrics_path,
    ),
    [selected_date, selected_city, selected_city, selected_date],
).fetch_arrow_table()
st.dataframe(
    environmental_metrics,
    width="stretch",
    column_config={
        "forecast_maximum": st.column_config.NumberColumn(
            "Forecast maximum", help="Maximum forecast value for the selected date."
        ),
        "historical_p95": st.column_config.NumberColumn(
            "Historical p95", help="Value exceeded by roughly five percent of historical observations."
        ),
    },
)

st.subheader("Affected Members")
st.caption("Ordered by contact priority, then the number of affected members in the city.")
table_filter_columns = st.columns(6)
condition = table_filter_columns[0].selectbox("Environmental condition", ["All", *sorted({
    row[1] for row in connection.execute(
        render_sql("dashboard/environmental_ticker.sql", environmental_conditions_path=conditions_path),
        [selected_date, selected_city, selected_city],
    ).fetchall()
    if row[1]
})])
severity = table_filter_columns[1].selectbox("Severity", ["All", "critical", "high", "medium", "low"])
contact_mode = table_filter_columns[2].selectbox("Contact mode", ["All", "app", "sms", "call"])
member_condition = table_filter_columns[3].selectbox(
    "Existing condition", ["All", "cardiovascular", "diabetes", "renal", "respiratory"]
)
minimum_priority = table_filter_columns[4].number_input(
    "Minimum priority", min_value=1, max_value=7, value=1
)
contactability = table_filter_columns[5].selectbox(
    "Contactability", ["All", "Contactable", "Not contactable"]
)
selected_condition = None if condition == "All" else condition
selected_severity = None if severity == "All" else severity
selected_contact_mode = None if contact_mode == "All" else contact_mode
selected_member_condition = None if member_condition == "All" else member_condition
selected_contactability = (
    None if contactability == "All" else contactability == "Contactable"
)
member_table = connection.execute(
    render_sql("dashboard/member_risk_exposure.sql", member_risk_exposure_path=member_risk_path),
    [
        selected_date, selected_date,
        selected_city, selected_city,
        selected_condition, selected_condition,
        selected_severity, selected_severity,
        selected_contact_mode, selected_contact_mode,
        selected_member_condition, selected_member_condition,
        minimum_priority, minimum_priority,
        selected_contactability, selected_contactability,
    ],
).fetch_arrow_table()
st.dataframe(
    member_table,
    width="stretch",
    column_config={
        "priority_score": st.column_config.NumberColumn(
            "Contact priority", help="Combines environmental severity, condition relevance, and age band."
        ),
        "outreach_eligible": st.column_config.CheckboxColumn(
            "Contactable", help="Whether outreach consent and cooldown requirements are satisfied."
        ),
    },
)

st.subheader("Insights")
chart_columns = st.columns(3)
city_comparison = connection.execute(
    render_sql("dashboard/city_comparison.sql", care_workload_path=workload_path), [selected_date]
).fetch_arrow_table()
chart_columns[0].caption("City comparison")
chart_columns[0].bar_chart(
    city_comparison, x="city_id", y=["at_risk_members", "contactable_members"], stack=False
)
severity_summary = connection.execute(
    render_sql("dashboard/severity_summary.sql", member_risk_exposure_path=member_risk_path),
    [selected_date, selected_city, selected_city],
).fetch_arrow_table()
chart_columns[1].caption("Severity summary")
chart_columns[1].bar_chart(severity_summary, x="severity", y="at_risk_members")
contact_summary = connection.execute(
    render_sql("dashboard/contact_mode_summary.sql", member_risk_exposure_path=member_risk_path),
    [selected_date, selected_city, selected_city],
).fetch_arrow_table()
chart_columns[2].caption("Contactable workload by mode")
chart_columns[2].bar_chart(contact_summary, x="contact_mode", y="contactable_members")

st.caption("At-risk member trend from the latest successful snapshot available for each date.")
trend = connection.execute(
    render_sql("dashboard/risk_trend.sql", care_workload_history_path=CARE_WORKLOAD_HISTORY),
    [selected_city, selected_city],
).fetch_arrow_table()
st.line_chart(trend, x="decision_date", y=["at_risk_members", "contactable_members"])

with st.expander("Pipeline Health And Quality"):
    metadata = MetadataStore()
    latest_run = metadata.latest_published_run()
    if latest_run:
        run_id = latest_run["run_id"]
        st.caption(f"Latest published pipeline run: `{run_id}` · status `{latest_run['status']}`")
        st.dataframe(
            [dict(row) for row in metadata.query("queries/latest_source_readiness.sql", (run_id,))],
            width="stretch",
        )
        st.dataframe(
            [dict(row) for row in metadata.query("queries/latest_quality_results.sql", (run_id,))],
            width="stretch",
        )
    metadata.close()

st.warning("Synthetic demonstration data only. This product does not provide medical advice or clinical risk scores.")
connection.close()
