"""
Influencers Performance Dashboard — FY26
=========================================
A Streamlit dashboard for tracking influencer-driven sales performance on a
monthly basis. Metric of interest is "Quantity Purchased (MT)" generated through
influencers across distributors and dealers.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
DATA_PATH = Path(__file__).parent / "data" / "Influencer_data_FY26.xlsx"

# Brand-ish palette
PRIMARY = "#1f4e79"
ACCENT = "#e07b39"
SEQ = px.colors.sequential.Blues

st.set_page_config(
    page_title="Influencers Performance — FY26",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# --------------------------------------------------------------------------- #
# Data loading & cleaning
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def load_data(source: bytes | Path = DATA_PATH) -> pd.DataFrame:
    """Read the influencer workbook and return a tidy, typed dataframe."""
    if isinstance(source, (bytes, bytearray)):
        df = pd.read_excel(io.BytesIO(source))
    else:
        df = pd.read_excel(source)

    df = df.rename(
        columns={
            "Distributor Name": "Distributor",
            "Account SF ID of Influencer": "Influencer_ID",
            "Name of Influencer": "Influencer",
            "Account SF ID of Dealer": "Dealer_ID",
            "Name of Dealer": "Dealer",
            "Quantity Purchased (MT)": "Quantity_MT",
            "Date of Purchase (MM-DD-YYYY)": "Purchase_Raw",
            "Remarks by SM": "SM_Remarks",
            "Remarks by Inside Sales (Verification Status)": "Verification_Status",
            "Phone Number": "Phone",
        }
    )

    # Parse purchase date — stored as "DD/MM/YYYY, h:mm am/pm"
    date_part = df["Purchase_Raw"].astype(str).str.split(",").str[0].str.strip()
    df["Purchase_Date"] = pd.to_datetime(
        date_part, format="%d/%m/%Y", errors="coerce"
    )

    # Derived time dimensions
    df["Month"] = df["Purchase_Date"].dt.to_period("M").astype(str)
    df["Month_Label"] = df["Purchase_Date"].dt.strftime("%b %Y")
    df["Day"] = df["Purchase_Date"].dt.date

    # Tidy strings / fills
    df["Distributor"] = df["Distributor"].fillna("Unknown").str.strip()
    df["Influencer"] = df["Influencer"].fillna("Unknown").str.strip()
    df["Dealer"] = df["Dealer"].fillna("Unknown").str.strip()
    df["Verification_Status"] = (
        df["Verification_Status"].fillna("Pending").astype(str).str.strip()
    )
    df["Quantity_MT"] = pd.to_numeric(df["Quantity_MT"], errors="coerce").fillna(0.0)

    # Clean phone (stored as float)
    df["Phone"] = (
        df["Phone"]
        .astype("Float64")
        .apply(lambda x: "" if pd.isna(x) else str(int(x)))
    )

    return df


def fmt(num: float, suffix: str = "") -> str:
    """Human-friendly number formatting."""
    if num >= 1_000_000:
        return f"{num/1_000_000:.2f}M{suffix}"
    if num >= 1_000:
        return f"{num/1_000:.2f}K{suffix}"
    return f"{num:,.2f}{suffix}" if isinstance(num, float) else f"{num:,}{suffix}"


# --------------------------------------------------------------------------- #
# Load
# --------------------------------------------------------------------------- #
st.sidebar.title("📊 Influencer Sales")
st.sidebar.caption("Performance Dashboard — FY26")

uploaded = st.sidebar.file_uploader(
    "Upload latest data (optional)", type=["xlsx"], help="Defaults to bundled FY26 data"
)

try:
    df = load_data(uploaded.getvalue()) if uploaded else load_data()
except FileNotFoundError:
    st.error(
        "Data file not found. Upload an `Influencer_data_FY26.xlsx` from the sidebar."
    )
    st.stop()


# --------------------------------------------------------------------------- #
# Sidebar filters
# --------------------------------------------------------------------------- #
st.sidebar.header("Filters")


def multiselect_all(label: str, options: list[str], key: str) -> list[str]:
    """A multiselect that treats 'empty' as 'all selected'."""
    opts = sorted(o for o in options if o)
    chosen = st.sidebar.multiselect(label, opts, default=[], key=key)
    return chosen if chosen else opts


months = multiselect_all("Month", df["Month_Label"].dropna().unique().tolist(), "f_month")
distributors = multiselect_all("Distributor", df["Distributor"].unique().tolist(), "f_dist")
statuses = multiselect_all(
    "Verification Status", df["Verification_Status"].unique().tolist(), "f_status"
)

influencer_search = st.sidebar.text_input("Search Influencer", "").strip().lower()
dealer_search = st.sidebar.text_input("Search Dealer", "").strip().lower()

# Quantity range
qmin, qmax = float(df["Quantity_MT"].min()), float(df["Quantity_MT"].max())
qty_range = st.sidebar.slider(
    "Quantity Purchased (MT)", qmin, qmax, (qmin, qmax)
)

# Apply filters
mask = (
    df["Month_Label"].isin(months)
    & df["Distributor"].isin(distributors)
    & df["Verification_Status"].isin(statuses)
    & df["Quantity_MT"].between(qty_range[0], qty_range[1])
)
if influencer_search:
    mask &= df["Influencer"].str.lower().str.contains(influencer_search, na=False)
if dealer_search:
    mask &= df["Dealer"].str.lower().str.contains(dealer_search, na=False)

fdf = df[mask].copy()


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
st.title("Influencers Performance Dashboard — FY26")
st.caption(
    "Monthly sales performance generated through influencers across distributors and dealers. "
    "Use the sidebar to slice by month, distributor, verification status and more."
)

if fdf.empty:
    st.warning("No records match the selected filters.")
    st.stop()


# --------------------------------------------------------------------------- #
# KPI row
# --------------------------------------------------------------------------- #
total_qty = fdf["Quantity_MT"].sum()
n_txn = len(fdf)
n_infl = fdf["Influencer"].nunique()
n_dist = fdf["Distributor"].nunique()
n_dealer = fdf["Dealer"].nunique()
avg_txn = fdf["Quantity_MT"].mean()
verified_share = (
    (fdf["Verification_Status"].eq("Completed").sum() / n_txn * 100) if n_txn else 0
)

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Total Volume (MT)", fmt(total_qty))
c2.metric("Transactions", f"{n_txn:,}")
c3.metric("Active Influencers", f"{n_infl:,}")
c4.metric("Distributors", f"{n_dist:,}")
c5.metric("Avg / Txn (MT)", f"{avg_txn:,.2f}")
c6.metric("Verified %", f"{verified_share:,.0f}%")

st.divider()


# --------------------------------------------------------------------------- #
# Tabs
# --------------------------------------------------------------------------- #
tab_overview, tab_influencers, tab_partners, tab_data = st.tabs(
    ["📈 Overview", "🧑‍🔧 Influencers", "🏭 Distributors & Dealers", "🗂️ Data"]
)

with tab_overview:
    col_a, col_b = st.columns([3, 2])

    # Monthly trend
    monthly = (
        fdf.groupby("Month_Label", as_index=False)["Quantity_MT"]
        .sum()
        .sort_values("Quantity_MT")
    )
    # keep chronological order based on underlying period
    order = (
        fdf.groupby("Month_Label")["Purchase_Date"].min().sort_values().index.tolist()
    )
    fig_month = px.bar(
        monthly,
        x="Month_Label",
        y="Quantity_MT",
        title="Volume by Month (MT)",
        text_auto=".1f",
        category_orders={"Month_Label": order},
        color_discrete_sequence=[PRIMARY],
    )
    fig_month.update_layout(xaxis_title="", yaxis_title="MT", showlegend=False)
    col_a.plotly_chart(fig_month, use_container_width=True)

    # Verification status donut
    status = fdf.groupby("Verification_Status", as_index=False)["Quantity_MT"].sum()
    fig_status = px.pie(
        status,
        names="Verification_Status",
        values="Quantity_MT",
        title="Volume by Verification Status",
        hole=0.5,
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    col_b.plotly_chart(fig_status, use_container_width=True)

    # Daily trend within selection
    daily = fdf.groupby("Day", as_index=False)["Quantity_MT"].sum().sort_values("Day")
    fig_daily = px.area(
        daily,
        x="Day",
        y="Quantity_MT",
        title="Daily Volume Trend (MT)",
        color_discrete_sequence=[ACCENT],
    )
    fig_daily.update_layout(xaxis_title="", yaxis_title="MT")
    st.plotly_chart(fig_daily, use_container_width=True)

with tab_influencers:
    top_n = st.slider("Show top N influencers", 5, 30, 15, key="topn_infl")
    infl = (
        fdf.groupby("Influencer", as_index=False)
        .agg(
            Volume_MT=("Quantity_MT", "sum"),
            Transactions=("Quantity_MT", "count"),
            Dealers=("Dealer", "nunique"),
        )
        .sort_values("Volume_MT", ascending=False)
    )
    fig_infl = px.bar(
        infl.head(top_n).sort_values("Volume_MT"),
        x="Volume_MT",
        y="Influencer",
        orientation="h",
        title=f"Top {top_n} Influencers by Volume (MT)",
        text_auto=".1f",
        color="Volume_MT",
        color_continuous_scale=SEQ,
    )
    fig_infl.update_layout(yaxis_title="", coloraxis_showscale=False, height=550)
    st.plotly_chart(fig_infl, use_container_width=True)

    st.subheader("Influencer Leaderboard")
    st.dataframe(
        infl.reset_index(drop=True),
        use_container_width=True,
        column_config={
            "Volume_MT": st.column_config.NumberColumn("Volume (MT)", format="%.2f"),
        },
    )

with tab_partners:
    col1, col2 = st.columns(2)

    dist = (
        fdf.groupby("Distributor", as_index=False)["Quantity_MT"]
        .sum()
        .sort_values("Quantity_MT", ascending=False)
    )
    fig_dist = px.bar(
        dist.head(15).sort_values("Quantity_MT"),
        x="Quantity_MT",
        y="Distributor",
        orientation="h",
        title="Top Distributors by Volume (MT)",
        text_auto=".1f",
        color_discrete_sequence=[PRIMARY],
    )
    fig_dist.update_layout(yaxis_title="", xaxis_title="MT", height=500)
    col1.plotly_chart(fig_dist, use_container_width=True)

    dealer = (
        fdf.groupby("Dealer", as_index=False)["Quantity_MT"]
        .sum()
        .sort_values("Quantity_MT", ascending=False)
    )
    fig_dealer = px.bar(
        dealer.head(15).sort_values("Quantity_MT"),
        x="Quantity_MT",
        y="Dealer",
        orientation="h",
        title="Top Dealers by Volume (MT)",
        text_auto=".1f",
        color_discrete_sequence=[ACCENT],
    )
    fig_dealer.update_layout(yaxis_title="", xaxis_title="MT", height=500)
    col2.plotly_chart(fig_dealer, use_container_width=True)

    # Distributor x Status breakdown
    pivot = (
        fdf.groupby(["Distributor", "Verification_Status"], as_index=False)[
            "Quantity_MT"
        ].sum()
    )
    top_dists = dist.head(12)["Distributor"].tolist()
    fig_stack = px.bar(
        pivot[pivot["Distributor"].isin(top_dists)],
        x="Quantity_MT",
        y="Distributor",
        color="Verification_Status",
        orientation="h",
        title="Distributor Volume by Verification Status",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig_stack.update_layout(yaxis_title="", xaxis_title="MT", height=500)
    st.plotly_chart(fig_stack, use_container_width=True)

with tab_data:
    st.subheader("Filtered Records")
    show_cols = [
        "Purchase_Date",
        "Month_Label",
        "Distributor",
        "Influencer",
        "Dealer",
        "Quantity_MT",
        "Verification_Status",
        "Phone",
    ]
    table = fdf[show_cols].sort_values("Purchase_Date", ascending=False)
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Purchase_Date": st.column_config.DateColumn("Purchase Date"),
            "Quantity_MT": st.column_config.NumberColumn("Quantity (MT)", format="%.2f"),
        },
    )

    csv = table.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download filtered data (CSV)",
        csv,
        file_name="influencer_performance_filtered.csv",
        mime="text/csv",
    )

st.caption(
    f"Showing {n_txn:,} of {len(df):,} records • Data: {df['Purchase_Date'].min():%d %b %Y} "
    f"– {df['Purchase_Date'].max():%d %b %Y}"
)
