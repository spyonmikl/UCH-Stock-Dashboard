"""
Pharmacy Stock Request Dashboard
=================================
Streamlit app for analysing hospital pharmacy stock request data.

Run from the project root:
    streamlit run tools/dashboard.py
"""

from pathlib import Path
import re
import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Pharmacy Stock Requests",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_PATH = Path(__file__).parent.parent / "Stock - Sept 24.xlsx"

# ---------------------------------------------------------------------------
# Data loading & cleaning
# ---------------------------------------------------------------------------
_SUFFIX_RE = re.compile(r"\s*[\{\(\[]\s*[A-Z0-9]{4,6}\s*[\}\)\]]\s*$")

_CD_MAP = {
    "Non-controlled Drugs": "Non-controlled",
    "Controlled Drugs": "Controlled",
    "Controlled drugs": "Controlled",
}


def _clean_item_name(raw: str) -> str:
    cleaned = _SUFFIX_RE.sub("", str(raw)).strip()
    return re.sub(r"  +", " ", cleaned)


@st.cache_data
def load_data(file_path: str) -> pd.DataFrame:
    df = pd.read_excel(file_path, engine="openpyxl")

    # 1. Strip column name whitespace (fixes "Value " trailing space)
    df.columns = df.columns.str.strip()

    # 2. Destination Location whitespace
    df["Destination Location"] = df["Destination Location"].astype(str).str.strip()

    # 3. Clean item names (strip trailing catalogue codes)
    df["Item Clean"] = df["Inventory Item"].apply(_clean_item_name)

    # 4. Normalise drug schedule
    df["Drug Schedule"] = (
        df["Controlled Drug Schedule"]
        .map(_CD_MAP)
        .fillna("Unknown")
    )

    # 5. Date column
    df["Date"] = pd.to_datetime(df["Date"])

    # 6. Fill null Submitting User (Direct Transfer rows)
    df["Submitting User"] = df["Submitting User"].fillna("UNATTRIBUTED")

    # 7. Value to numeric (coerce any errors to 0)
    df["Value"] = pd.to_numeric(df["Value"], errors="coerce").fillna(0)

    # 8. Period helpers
    df["Week"] = df["Date"].dt.to_period("W")
    df["Month"] = df["Date"].dt.to_period("M")

    return df


# ---------------------------------------------------------------------------
# Guard: file exists?
# ---------------------------------------------------------------------------
if not DATA_PATH.exists():
    st.error(
        f"Data file not found: `{DATA_PATH}`\n\n"
        "Ensure **Stock - Sept 24.xlsx** is in the project root directory."
    )
    st.stop()

df = load_data(str(DATA_PATH))

# ---------------------------------------------------------------------------
# Sidebar — controls
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("Filters")
    st.markdown("---")

    # --- Time frame ---
    time_mode = st.radio("Time Frame", ["Daily", "Weekly", "Monthly"], index=2)

    min_date = df["Date"].min().date()
    max_date = df["Date"].max().date()

    if time_mode == "Daily":
        selected_date = st.date_input(
            "Select Date",
            value=max_date,
            min_value=min_date,
            max_value=max_date,
        )
        time_mask = df["Date"].dt.date == selected_date
        display_period = selected_date.strftime("%A %d %B %Y")
        week_start = week_end = None

    elif time_mode == "Weekly":
        week_periods = sorted(df["Week"].unique())
        week_labels: dict[str, tuple[datetime.date, datetime.date]] = {}
        for p in week_periods:
            start = p.start_time.date()
            end = p.end_time.date()
            iso_week = p.start_time.isocalendar()[1]
            label = f"Week {iso_week}  ({start.strftime('%b %d')} – {end.strftime('%b %d')})"
            week_labels[label] = (start, end)

        selected_week_label = st.selectbox(
            "Select Week",
            options=list(week_labels.keys()),
            index=len(week_labels) - 1,
        )
        week_start, week_end = week_labels[selected_week_label]
        time_mask = (df["Date"].dt.date >= week_start) & (df["Date"].dt.date <= week_end)
        display_period = selected_week_label
        selected_date = None

    else:  # Monthly
        month_periods = sorted(df["Month"].unique())
        month_labels: dict[str, object] = {
            p.start_time.strftime("%B %Y"): p for p in month_periods
        }
        selected_month_label = st.selectbox(
            "Select Month",
            options=list(month_labels.keys()),
            index=len(month_labels) - 1,
        )
        selected_period = month_labels[selected_month_label]
        time_mask = df["Month"] == selected_period
        display_period = selected_month_label
        selected_date = week_start = week_end = None

    # --- Ward filter ---
    st.markdown("---")
    all_destinations = sorted(df["Destination Location"].unique())
    selected_destinations = st.multiselect(
        "Ward / Destination (optional)",
        options=all_destinations,
        default=[],
        placeholder="All wards",
    )

    # --- Drug schedule ---
    st.markdown("---")
    schedule_options = ["Non-controlled", "Controlled", "Unknown"]
    selected_schedules = st.multiselect(
        "Drug Schedule",
        options=schedule_options,
        default=schedule_options,
    )

    # --- Top N ---
    st.markdown("---")
    top_n = st.slider("Top N results", min_value=5, max_value=50, value=20, step=5)

# ---------------------------------------------------------------------------
# Apply filters
# ---------------------------------------------------------------------------
filtered_df = df[time_mask].copy()

if selected_destinations:
    filtered_df = filtered_df[filtered_df["Destination Location"].isin(selected_destinations)]

if selected_schedules:
    filtered_df = filtered_df[filtered_df["Drug Schedule"].isin(selected_schedules)]

# Guard: empty result
if filtered_df.empty:
    st.warning("No data matches the selected filters. Adjust the sidebar controls.")
    st.stop()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("Pharmacy Stock Request Dashboard")
st.caption(f"Showing: **{display_period}**  •  Source: `{DATA_PATH.name}`")
st.markdown("---")

# ---------------------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------------------
total_requests = filtered_df["Request Number"].nunique()
total_lines = len(filtered_df)
total_value = filtered_df["Value"].sum()
unique_wards = filtered_df["Destination Location"].nunique()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Unique Requests", f"{total_requests:,}")
k2.metric("Line Items", f"{total_lines:,}")
k3.metric("Total Value", f"£{total_value:,.2f}")
k4.metric("Unique Wards", f"{unique_wards:,}")

st.markdown("---")

# ---------------------------------------------------------------------------
# Section 1 — Requests per Ward
# ---------------------------------------------------------------------------
st.subheader("1. Requests per Ward")

tab_req, tab_lines_ward = st.tabs(["By Unique Requests", "By Line Items"])

with tab_req:
    ward_req = (
        filtered_df.groupby("Destination Location")["Request Number"]
        .nunique()
        .reset_index()
        .rename(columns={"Request Number": "Unique Requests"})
        .sort_values("Unique Requests", ascending=False)
    )
    fig = px.bar(
        ward_req.head(top_n),
        x="Unique Requests",
        y="Destination Location",
        orientation="h",
        title=f"Top {top_n} Wards by Unique Requests",
        color="Unique Requests",
        color_continuous_scale="Blues",
        labels={"Destination Location": "Ward / Destination"},
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=max(400, top_n * 22), showlegend=False)
    fig.update_coloraxes(showscale=False)
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Show full ward table"):
        st.dataframe(ward_req.reset_index(drop=True), use_container_width=True, hide_index=True)

with tab_lines_ward:
    ward_lines = (
        filtered_df.groupby("Destination Location")
        .size()
        .reset_index(name="Line Items")
        .sort_values("Line Items", ascending=False)
    )
    fig2 = px.bar(
        ward_lines.head(top_n),
        x="Line Items",
        y="Destination Location",
        orientation="h",
        title=f"Top {top_n} Wards by Line Items",
        color="Line Items",
        color_continuous_scale="Greens",
        labels={"Destination Location": "Ward / Destination"},
    )
    fig2.update_layout(yaxis={"categoryorder": "total ascending"}, height=max(400, top_n * 22), showlegend=False)
    fig2.update_coloraxes(showscale=False)
    st.plotly_chart(fig2, use_container_width=True)

    with st.expander("Show full ward table"):
        st.dataframe(ward_lines.reset_index(drop=True), use_container_width=True, hide_index=True)

st.markdown("---")

# ---------------------------------------------------------------------------
# Section 2 — Inventory Item Breakdown
# ---------------------------------------------------------------------------
st.subheader("2. Inventory Item Breakdown")

item_agg = (
    filtered_df.groupby("Item Clean")
    .agg(
        Total_Quantity=("Quantity", "sum"),
        Total_Value=("Value", "sum"),
        Requests=("Request Number", "nunique"),
    )
    .reset_index()
    .sort_values("Total_Quantity", ascending=False)
)

tab_item_chart, tab_item_table = st.tabs(["Chart (Top N by Quantity)", "Full Table"])

with tab_item_chart:
    fig3 = px.bar(
        item_agg.head(top_n),
        x="Total_Quantity",
        y="Item Clean",
        orientation="h",
        title=f"Top {top_n} Items by Total Quantity Requested",
        color="Total_Value",
        color_continuous_scale="Viridis",
        hover_data={"Total_Value": ":,.2f", "Requests": True},
        labels={
            "Item Clean": "Inventory Item",
            "Total_Quantity": "Total Quantity",
            "Total_Value": "Total Value (£)",
        },
    )
    fig3.update_layout(yaxis={"categoryorder": "total ascending"}, height=max(400, top_n * 22))
    fig3.update_coloraxes(colorbar_title="Value (£)")
    st.plotly_chart(fig3, use_container_width=True)

with tab_item_table:
    st.dataframe(
        item_agg.rename(columns={
            "Item Clean": "Item Name",
            "Total_Quantity": "Total Qty",
            "Total_Value": "Total Value (£)",
        }).reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
    )

st.markdown("---")

# ---------------------------------------------------------------------------
# Section 3 — Total Value per Stock Item
# ---------------------------------------------------------------------------
st.subheader("3. Total Value per Stock Item (£)")

item_value = (
    filtered_df.groupby("Item Clean")["Value"]
    .sum()
    .reset_index()
    .sort_values("Value", ascending=False)
)

fig4 = px.bar(
    item_value.head(top_n),
    x="Value",
    y="Item Clean",
    orientation="h",
    title=f"Top {top_n} Items by Total £ Value",
    color="Value",
    color_continuous_scale="Reds",
    labels={"Item Clean": "Inventory Item", "Value": "Total Value (£)"},
)
fig4.update_layout(
    yaxis={"categoryorder": "total ascending"},
    xaxis_tickformat=",.0f",
    height=max(400, top_n * 22),
)
fig4.update_coloraxes(showscale=False)
st.plotly_chart(fig4, use_container_width=True)

# Treemap + Pie
col_tree, col_pie = st.columns([2, 1])

with col_tree:
    treemap_data = (
        filtered_df.groupby(["Drug Schedule", "Destination Location"])["Value"]
        .sum()
        .reset_index()
    )
    fig5 = px.treemap(
        treemap_data,
        path=["Drug Schedule", "Destination Location"],
        values="Value",
        title="Value Distribution: Drug Schedule → Ward",
        color="Value",
        color_continuous_scale="RdYlGn_r",
    )
    fig5.update_traces(textinfo="label+percent root")
    st.plotly_chart(fig5, use_container_width=True)

with col_pie:
    pie_data = filtered_df.groupby("Drug Schedule")["Value"].sum().reset_index()
    fig6 = px.pie(
        pie_data,
        names="Drug Schedule",
        values="Value",
        title="Controlled vs Non-controlled Value",
        color="Drug Schedule",
        color_discrete_map={
            "Non-controlled": "#2196F3",
            "Controlled": "#F44336",
            "Unknown": "#9E9E9E",
        },
        hole=0.4,
    )
    fig6.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig6, use_container_width=True)

st.markdown("---")

# ---------------------------------------------------------------------------
# Section 4 — Top Submitting Users
# ---------------------------------------------------------------------------
st.subheader("4. Top Submitting Users")

user_df = (
    filtered_df.groupby("Submitting User")
    .agg(
        Requests=("Request Number", "nunique"),
        Line_Items=("Quantity", "count"),
        Total_Value=("Value", "sum"),
    )
    .reset_index()
    .sort_values("Requests", ascending=False)
)

col_uchart, col_utable = st.columns([3, 2])

with col_uchart:
    fig7 = px.bar(
        user_df.head(top_n),
        x="Requests",
        y="Submitting User",
        orientation="h",
        title=f"Top {top_n} Users by Requests Submitted",
        color="Total_Value",
        color_continuous_scale="Purples",
        hover_data={"Line_Items": True, "Total_Value": ":,.2f"},
        labels={
            "Submitting User": "Staff Member",
            "Requests": "Unique Requests",
            "Total_Value": "Value (£)",
        },
    )
    fig7.update_layout(yaxis={"categoryorder": "total ascending"}, height=max(400, top_n * 22))
    fig7.update_coloraxes(colorbar_title="Value (£)")
    st.plotly_chart(fig7, use_container_width=True)

with col_utable:
    ranked_users = (
        user_df.head(top_n)
        .reset_index(drop=True)
        .assign(Rank=lambda d: d.index + 1)
        [["Rank", "Submitting User", "Requests", "Line_Items", "Total_Value"]]
        .rename(columns={
            "Submitting User": "Staff Member",
            "Line_Items": "Line Items",
            "Total_Value": "Total Value (£)",
        })
    )
    ranked_users["Total Value (£)"] = ranked_users["Total Value (£)"].map("£{:,.2f}".format)
    st.dataframe(ranked_users, use_container_width=True, hide_index=True)

st.markdown("---")

# ---------------------------------------------------------------------------
# Section 5 — Daily trend (hidden in Monthly mode)
# ---------------------------------------------------------------------------
if time_mode != "Monthly":
    st.subheader("5. Daily Request Volume (Full Period Context)")

    daily_trend = (
        df.groupby(df["Date"].dt.date)  # always full dataset
        .agg(Requests=("Request Number", "nunique"), Value=("Value", "sum"))
        .reset_index()
        .rename(columns={"Date": "date"})
    )

    fig8 = px.line(
        daily_trend,
        x="date",
        y="Requests",
        title="Daily Unique Requests — September 2024",
        markers=True,
        labels={"date": "Date", "Requests": "Unique Requests"},
    )
    fig8.update_traces(line_color="#1976D2", marker_color="#1976D2")

    if time_mode == "Daily" and selected_date is not None:
        fig8.add_vline(
            x=str(selected_date),
            line_dash="dash",
            line_color="red",
            annotation_text="Selected",
            annotation_position="top right",
        )
    elif time_mode == "Weekly" and week_start is not None and week_end is not None:
        fig8.add_vrect(
            x0=str(week_start),
            x1=str(week_end),
            fillcolor="orange",
            opacity=0.2,
            line_width=0,
            annotation_text="Selected week",
            annotation_position="top left",
        )

    fig8.update_layout(height=320)
    st.plotly_chart(fig8, use_container_width=True)

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.caption(
    f"Data loaded from `{DATA_PATH.name}` · "
    f"{len(df):,} total rows · "
    f"Date range: {min_date.strftime('%d %b %Y')} – {max_date.strftime('%d %b %Y')}"
)
