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


def display_text(value: str) -> str:
    result = value.replace("_", " ").title()
    return result.replace("Pm2 5", "PM2.5").replace("Pm10", "PM10").replace("24H", "24h")


st.set_page_config(page_title="CareSignal India", layout="wide")
runtime = load_runtime_settings()
today = datetime.now(ZoneInfo(runtime.decision_timezone)).date()

if not DATABASE_PATH.exists() or not HISTORY_ROOT.exists():
    st.title("CareSignal India")
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
today_snapshot_run = run_by_date.get(today)
today_temperature = None
if today_snapshot_run:
    today_temperature = connection.execute(
        render_sql(
            "dashboard/today_temperature.sql",
            environmental_metrics_path=(
                HISTORY_ROOT / f"run_id={today_snapshot_run}/environmental_metrics_daily.parquet"
            ),
        ),
        [today],
    ).fetchone()
temperature_text = "Not Available"
if today_temperature and today_temperature[1] is not None:
    temperature_text = (
        f"{today_temperature[0]:.1f}–{today_temperature[2]:.1f} °C"
        f"<br><small>Average {today_temperature[1]:.1f} °C</small>"
    )

title_column, date_column = st.columns([4, 1])
title_column.title("CareSignal India")
title_column.caption("Year-round environmental care-operations intelligence using synthetic member data.")
date_column.markdown(
    f"<div style='text-align:right'><b>Today</b><br>{today.strftime('%d %B %Y')}"
    f"<br><br><b>Today's Temperature</b><br>{temperature_text}</div>",
    unsafe_allow_html=True,
)

default_date = today if today in run_by_date else available_dates[-1]
selected_date = st.date_input(
    "Date",
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

ticker_rows = connection.execute(
    render_sql("dashboard/environmental_ticker.sql", environmental_conditions_path=conditions_path),
    [selected_date, None, None],
).fetchall()
ticker_items = [
    f"{display_text(row[0])}: {display_text(row[1])} ({display_text(row[2])}) · "
    f"{display_text(row[3])} · {row[4]}h"
    for row in ticker_rows
]
ticker_text = "   •   ".join(html.escape(item) for item in ticker_items) or "No Active Environmental Risks"
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
    [selected_date, None, None],
).fetchone()
total_members, at_risk, at_risk_pct, contactable, high_priority, affected_cities = kpis
kpi_columns = st.columns(5)
kpi_columns[0].metric(
    "Potentially At-Risk Members",
    f"{at_risk or 0:,}",
    f"{at_risk_pct or 0:.2f}% of {total_members or 0:,}",
    help="Distinct active members whose city, conditions, and selected-date environmental risks match.",
)
kpi_columns[1].metric(
    "Contactable At-Risk Members",
    f"{contactable or 0:,}",
    help="At-risk members with outreach consent who are outside the configured contact cooldown.",
)
kpi_columns[2].metric(
    "High-Priority Members",
    f"{high_priority or 0:,}",
    help="Distinct at-risk members with priority score of four or higher.",
)
kpi_columns[3].metric(
    "Affected Cities",
    f"{affected_cities or 0:,}",
    help="Publication-approved cities with at least one potentially at-risk member.",
)
kpi_columns[4].metric(
    "Active Conditions",
    f"{len(ticker_rows):,}",
    help="Distinct city-level environmental conditions active on the selected date.",
)

st.caption(
    f"Selected date `{selected_date}` · latest matching snapshot `{snapshot_run_id}` · "
    f"history retention `{runtime.analytical_history_retention_days}` days"
)

st.subheader("Environmental Metrics")
environmental_metrics = connection.execute(
    render_sql(
        "dashboard/environmental_metrics_daily.sql",
        environmental_conditions_path=conditions_path,
        environmental_metrics_path=metrics_path,
    ),
    [selected_date, None, None, selected_date],
).fetch_arrow_table()
st.dataframe(
    environmental_metrics,
    width="stretch",
    column_config={
        "forecast_maximum": st.column_config.NumberColumn(
            "Forecast Maximum", help="Maximum forecast value for the selected date."
        ),
        "historical_p95": st.column_config.NumberColumn(
            "Historical P95", help="Value exceeded by roughly five percent of historical observations."
        ),
    },
)

st.subheader("Affected Members")
st.caption("Ordered by contact priority, then the number of affected members in the city.")
table_filters = st.columns(2)
city = table_filters[0].selectbox("City", ["All", *[city.city_id for city in load_cities()]])
severity = table_filters[1].selectbox("Severity", ["All", "critical", "high", "medium", "low"])
selected_city = None if city == "All" else city
selected_severity = None if severity == "All" else severity
member_table = connection.execute(
    render_sql("dashboard/member_risk_exposure.sql", member_risk_exposure_path=member_risk_path),
    [selected_date, selected_date, selected_city, selected_city, selected_severity, selected_severity],
).fetch_arrow_table()
st.dataframe(
    member_table,
    width="stretch",
    column_config={
        "priority_score": st.column_config.NumberColumn(
            "Contact Priority", help="Combines environmental severity, condition relevance, and age band."
        ),
        "outreach_eligible": st.column_config.CheckboxColumn(
            "Contactable", help="Whether outreach consent and cooldown requirements are satisfied."
        ),
    },
)

st.subheader("Care Operations Insights")
outreach_readiness = connection.execute(
    render_sql("dashboard/outreach_readiness_by_city.sql", care_workload_path=workload_path),
    [selected_date],
).fetch_arrow_table()
risk_drivers = connection.execute(
    render_sql("dashboard/risk_driver_impact.sql", member_risk_exposure_path=member_risk_path),
    [selected_date],
).fetch_arrow_table()
condition_workload = connection.execute(
    render_sql("dashboard/condition_workload.sql", member_risk_exposure_path=member_risk_path),
    [selected_date],
).fetch_arrow_table()
channel_workload = connection.execute(
    render_sql("dashboard/contact_channel_workload.sql", member_risk_exposure_path=member_risk_path),
    [selected_date],
).fetch_arrow_table()

readiness_rows = outreach_readiness.to_pylist()
driver_rows = risk_drivers.to_pylist()
highest_burden = readiness_rows[0] if readiness_rows else None
largest_gap = max(readiness_rows, key=lambda row: row["outreach_gap"]) if readiness_rows else None
dominant_driver = driver_rows[0] if driver_rows else None
insight_columns = st.columns(3)
insight_columns[0].metric(
    "Highest-Burden City",
    display_text(highest_burden["city_id"]) if highest_burden else "None",
    f"{highest_burden['at_risk_members']:,} at-risk members" if highest_burden else None,
    help="City with the largest number of potentially at-risk members.",
)
insight_columns[1].metric(
    "Largest Outreach Gap",
    display_text(largest_gap["city_id"]) if largest_gap else "None",
    f"{largest_gap['outreach_gap']:,} members not currently contactable" if largest_gap else None,
    help="City where the most at-risk members cannot currently be contacted due to consent or cooldown.",
)
insight_columns[2].metric(
    "Dominant Risk Driver",
    dominant_driver["environmental_condition"] if dominant_driver else "None",
    f"{dominant_driver['at_risk_members']:,} members affected" if dominant_driver else None,
    help="Environmental condition affecting the largest number of distinct members.",
)

chart_columns = st.columns(2)
chart_columns[0].caption("Outreach Readiness By City")
chart_columns[0].bar_chart(
    outreach_readiness, x="city_id", y=["contactable_members", "outreach_gap"], stack=True
)
chart_columns[1].caption("Member Impact By Environmental Risk Driver")
chart_columns[1].bar_chart(risk_drivers, x="environmental_condition", y="at_risk_members")
chart_columns = st.columns(2)
chart_columns[0].caption("Vulnerable Cohort Workload")
chart_columns[0].bar_chart(
    condition_workload,
    x="member_condition",
    y=["contactable_members", "high_priority_members"],
    stack=False,
)
chart_columns[1].caption("Recommended Contact-Channel Demand")
chart_columns[1].bar_chart(
    channel_workload,
    x="contact_channel",
    y=["contactable_members", "high_priority_members"],
    stack=False,
)

st.caption("Daily at-risk and contactable-member demand across the retained forecast horizon.")
trend = connection.execute(
    render_sql("dashboard/risk_trend.sql", care_workload_history_path=CARE_WORKLOAD_HISTORY),
    [None, None],
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
