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

# Access control — password determines the role.
#   Admin   : full access, including the data-upload option.
#   Viewer  : read-only dashboard, no upload.
# NOTE: For a production deployment, move these into st.secrets instead of code.
PASSWORDS = {
    "9999": "admin",
    "1111": "viewer",
}

# Master access switch. When False, the dashboard is fully locked down — every
# login (viewer, influencer and admin) is blocked and a notice is shown instead.
ACCESS_ENABLED = False

# --------------------------------------------------------------------------- #
# Influencer Scheme — JSW One TMT (Q1 FY26-27, 1 Apr – 30 Jun 2026)
# Gift is decided by an influencer's CUMULATIVE Quantity (MT) over the period.
# Each slab is (lower_bound, upper_inclusive, gift); the first slab starts at 3.
# --------------------------------------------------------------------------- #
SCHEME_PERIOD = "1st April 2026 – 30th June 2026 (Q1 FY26-27)"
SLABS = [
    (3, 5, "Portable Blender"),
    (5, 10, "Pedestal Fan"),
    (10, 20, "Tower Fan"),
    (20, 35, "Air Cooler"),
    (35, 50, "Fridge"),
    (50, 75, "Air Conditioner"),
    (75, float("inf"), "International Trip"),
]
# Pretty range labels matching the official scheme flyer.
SCHEME_RANGE_LABELS = [
    "3 – 5", ">5 – 10", ">10 – 20", ">20 – 35", ">35 – 50", ">50 – 75", ">75",
]

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
# Scheme helpers
# --------------------------------------------------------------------------- #
def assign_gift(qty: float) -> str:
    """Return the gift an influencer qualifies for at a cumulative volume."""
    if qty < SLABS[0][0]:
        return "Not qualified"
    for _lo, hi, gift in SLABS:
        if qty <= hi:
            return gift
    return SLABS[-1][2]


def next_gift(qty: float) -> tuple[str | None, float]:
    """Return (next gift, MT still needed) — or (None, 0) at the top slab."""
    if qty < SLABS[0][0]:
        return SLABS[0][2], round(SLABS[0][0] - qty, 2)
    for i, (_lo, hi, _gift) in enumerate(SLABS):
        if qty <= hi:
            if hi == float("inf"):
                return None, 0.0
            return SLABS[i + 1][2], round(hi - qty, 2)
    return None, 0.0


def scheme_table() -> pd.DataFrame:
    """The official slab → gift reference table."""
    return pd.DataFrame(
        {
            "Quantity (MT)": SCHEME_RANGE_LABELS,
            "Gift": [g for _lo, _hi, g in SLABS],
        }
    )


def qualifiers(full_df: pd.DataFrame) -> pd.DataFrame:
    """Per-influencer (Name + Phone) cumulative volume and qualified gift."""
    q = (
        full_df.groupby(["Influencer", "Phone"], as_index=False)["Quantity_MT"]
        .sum()
        .rename(columns={"Quantity_MT": "Total_MT"})
        .sort_values("Total_MT", ascending=False)
    )
    q["Gift"] = q["Total_MT"].apply(assign_gift)
    return q


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
def phone_directory(df: pd.DataFrame) -> dict[str, str]:
    """Map each known phone number -> influencer name (for influencer logins)."""
    valid = df[df["Phone"] != ""]
    return valid.groupby("Phone")["Influencer"].first().to_dict()


def require_login(df: pd.DataFrame) -> dict:
    """Gate the app behind a password and return the resolved session info.

    A password can be one of:
      * an admin / viewer password (see ``PASSWORDS``), or
      * an influencer's phone number — which scopes the view to their own data.

    Returns a dict: ``{"role", "phone", "name"}``. Stops execution and renders
    a login form until a valid password is entered.
    """
    if st.session_state.get("auth"):
        return st.session_state["auth"]

    st.title("🔒 Influencers Performance Dashboard — FY26")
    st.caption(
        "Enter your access password to continue. "
        "Influencers: use your registered phone number to view your own data."
    )

    with st.form("login_form"):
        pwd = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")

    if submitted:
        entry = pwd.strip()
        directory = phone_directory(df)
        if entry in PASSWORDS:
            auth = {"role": PASSWORDS[entry], "phone": None, "name": None}
        elif entry in directory:
            auth = {"role": "influencer", "phone": entry, "name": directory[entry]}
        else:
            auth = None

        if auth:
            st.session_state["auth"] = auth
            st.rerun()
        else:
            st.error("Incorrect password. Please try again.")

    st.stop()


# Master lockdown — block all access before any data load or login.
if not ACCESS_ENABLED:
    # Completely blank page — hide Streamlit chrome and show only "offline".
    st.markdown(
        """
        <style>
            #MainMenu, header, footer {visibility: hidden;}
            .stApp {background: #ffffff;}
            .offline {
                position: fixed; top: 50%; left: 50%;
                transform: translate(-50%, -50%);
                font-size: 2rem; color: #888; font-family: sans-serif;
            }
        </style>
        <div class="offline">offline</div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

# Load the bundled dataset first so influencer phone logins can be validated.
try:
    base_df = load_data()
except FileNotFoundError:
    st.error("Data file not found. Place `Influencer_data_FY26.xlsx` under `data/`.")
    st.stop()

auth = require_login(base_df)
role = auth["role"]
is_admin = role == "admin"
is_influencer = role == "influencer"


# --------------------------------------------------------------------------- #
# Load
# --------------------------------------------------------------------------- #
st.sidebar.title("📊 Influencer Sales")
st.sidebar.caption("Performance Dashboard — FY26")

# Show who is signed in + a sign-out control.
if is_influencer:
    st.sidebar.success(f"Signed in as **{auth['name']}**")
    st.sidebar.caption("Influencer view — showing only your data")
else:
    st.sidebar.success(f"Signed in as **{role.title()}**")
if st.sidebar.button("Sign out"):
    st.session_state.pop("auth", None)
    st.rerun()

# Upload is an admin-only capability.
if is_admin:
    uploaded = st.sidebar.file_uploader(
        "Upload latest data", type=["xlsx"], help="Defaults to bundled FY26 data"
    )
    if uploaded is not None:
        st.sidebar.caption("Previewing uploaded file in this session.")
        if st.sidebar.button("💾 Save as default dataset", type="primary"):
            data_bytes = uploaded.getvalue()
            try:
                load_data(data_bytes)  # validate it parses before persisting
            except Exception as exc:  # noqa: BLE001
                st.sidebar.error(f"Could not read this file: {exc}")
            else:
                DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
                DATA_PATH.write_bytes(data_bytes)
                load_data.clear()  # drop cached copy so everyone gets the new data
                st.sidebar.success(
                    "Saved. This is now the default dataset for all users."
                )
                st.rerun()
else:
    uploaded = None

try:
    df = load_data(uploaded.getvalue()) if uploaded else base_df
except FileNotFoundError:
    st.error(
        "Data file not found. Upload an `Influencer_data_FY26.xlsx` from the sidebar."
    )
    st.stop()

# Influencers only ever see their own rows.
if is_influencer:
    df = df[df["Phone"] == auth["phone"]].copy()
    if df.empty:
        st.warning("No records found for your account.")
        st.stop()


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
if is_influencer:
    st.title(f"Performance Dashboard — {auth['name']}")
    st.caption(
        "Your monthly sales performance. "
        "Use the filters below to slice by month, dealer and more."
    )
else:
    st.title("Influencers Performance Dashboard — FY26")
    st.caption(
        "Monthly sales performance generated through influencers across distributors and dealers. "
        "Use the filters below to slice by month, distributor, verification status and more."
    )


def influencer_rank(full_df: pd.DataFrame, name: str) -> tuple[int, int, float, float]:
    """Return (rank, total_influencers, own_volume, leader_volume) by volume."""
    board = full_df.groupby("Influencer")["Quantity_MT"].sum().sort_values(ascending=False)
    rank = int(board.index.get_loc(name)) + 1 if name in board.index else 0
    own = float(board.get(name, 0.0))
    leader = float(board.iloc[0]) if len(board) else 0.0
    return rank, len(board), own, leader


# Personalised rank + scheme callout — computed against ALL influencers (full data).
if is_influencer:
    rank, total, own_vol, leader_vol = influencer_rank(base_df, auth["name"])
    # Cumulative volume for the scheme uses this influencer's Name + Phone.
    my_total = float(
        base_df.loc[base_df["Phone"] == auth["phone"], "Quantity_MT"].sum()
    )
    my_gift = assign_gift(my_total)
    nxt, need = next_gift(my_total)
    top_pct = max(1, round(rank / total * 100)) if total else 0

    rc1, rc2, rc3, rc4 = st.columns(4)
    rc1.metric("🏆 Your Rank", f"#{rank} of {total}")
    rc2.metric("Your Volume (MT)", f"{my_total:,.2f}")
    rc3.metric("Standing", f"Top {top_pct}%")
    rc4.metric("🎁 You've Won", my_gift)

    if my_gift == "Not qualified":
        st.warning(
            f"You need **{need:,.2f} MT** more to unlock your first gift "
            f"(**{nxt}** at 3 MT). Keep going!"
        )
    elif nxt:
        st.success(
            f"You've qualified for a **{my_gift}**! "
            f"Just **{need:,.2f} MT** more to upgrade to a **{nxt}**. 🚀"
        )
    else:
        st.success(
            f"Incredible — you've qualified for the top reward, an **{my_gift}**! 🌍✈️"
        )
    st.caption(f"Scheme period: {SCHEME_PERIOD}. Gift based on your cumulative volume.")


# --------------------------------------------------------------------------- #
# Filters — on the main page so everyone can see and apply them
# --------------------------------------------------------------------------- #
def multiselect_all(container, label: str, options: list[str], key: str) -> list[str]:
    """A multiselect that treats 'empty' as 'all selected'."""
    opts = sorted(o for o in options if o)
    chosen = container.multiselect(label, opts, default=[], key=key)
    return chosen if chosen else opts


with st.expander("🔎 Filters", expanded=True):
    fc1, fc2, fc3, fc4 = st.columns(4)
    months = multiselect_all(
        fc1, "Month", df["Month_Label"].dropna().unique().tolist(), "f_month"
    )
    distributors = multiselect_all(
        fc2, "Distributor", df["Distributor"].unique().tolist(), "f_dist"
    )
    influencers = multiselect_all(
        fc3, "Influencer", df["Influencer"].unique().tolist(), "f_infl"
    )
    dealers = multiselect_all(
        fc4, "Dealer", df["Dealer"].unique().tolist(), "f_dealer"
    )

# Apply filters
mask = (
    df["Month_Label"].isin(months)
    & df["Distributor"].isin(distributors)
    & df["Influencer"].isin(influencers)
    & df["Dealer"].isin(dealers)
)

fdf = df[mask].copy()

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
tab_overview, tab_scheme, tab_influencers, tab_partners, tab_data = st.tabs(
    [
        "📈 Overview",
        "🎁 Scheme & Rewards",
        "🧑‍🔧 Influencers",
        "🏭 Distributors & Dealers",
        "🗂️ Data",
    ]
)

with tab_scheme:
    st.subheader("JSW One TMT — Influencer Scheme")
    st.caption(f"Win exciting prizes • {SCHEME_PERIOD}")

    left, right = st.columns([3, 2])
    with left:
        st.markdown("**Reward slabs** — gift by cumulative Quantity (MT)")
        st.dataframe(scheme_table(), hide_index=True, use_container_width=True)
    with right:
        st.markdown("**Qualifying criteria**")
        st.markdown(
            "- Consumer sales through Contractor/Mason must be recorded with the "
            "dealer/distributor.\n"
            "- Total sales of dealer through contractor/mason in Q1 FY26-27 "
            "(1st April – 30th June) are considered for the qualifying slab.\n"
            "- Each influencer is identified uniquely by **name + phone number**.\n"
            "- Verification (Name, Mobile, Address, KYC) is mandatory before gift "
            "disbursement."
        )

    if is_influencer:
        # Personal scheme status was shown in the callout above; reinforce here.
        st.info(
            f"**{auth['name']}** — cumulative **{my_total:,.2f} MT** → "
            f"**{my_gift}**"
            + (f" • {need:,.2f} MT more for a {nxt}." if nxt else " (top reward!).")
        )
    else:
        # Admin / viewer: full qualification roster + slab distribution.
        qual = qualifiers(base_df)
        qualified = qual[qual["Gift"] != "Not qualified"]
        k1, k2, k3 = st.columns(3)
        k1.metric("Total Influencers", f"{len(qual):,}")
        k2.metric("Qualified for a Gift", f"{len(qualified):,}")
        k3.metric("International Trip Winners", f"{(qual['Gift'] == 'International Trip').sum():,}")

        gift_order = [g for _lo, _hi, g in SLABS] + ["Not qualified"]
        dist_counts = (
            qual["Gift"].value_counts().reindex(gift_order).fillna(0).astype(int)
        )
        fig_gift = px.bar(
            x=dist_counts.values,
            y=dist_counts.index,
            orientation="h",
            title="Influencers by Reward Slab",
            text=dist_counts.values,
            color=dist_counts.values,
            color_continuous_scale=SEQ,
        )
        fig_gift.update_layout(
            xaxis_title="Influencers", yaxis_title="", coloraxis_showscale=False,
            yaxis={"categoryorder": "array", "categoryarray": gift_order[::-1]},
        )
        st.plotly_chart(fig_gift, use_container_width=True)

        st.subheader("Qualification Roster")
        gift_filter = st.multiselect(
            "Filter by gift", gift_order, default=[], key="scheme_gift"
        )
        roster = qual if not gift_filter else qual[qual["Gift"].isin(gift_filter)]
        st.dataframe(
            roster.reset_index(drop=True),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Total_MT": st.column_config.NumberColumn("Total (MT)", format="%.2f"),
            },
        )
        st.download_button(
            "⬇️ Download qualification roster (CSV)",
            roster.to_csv(index=False).encode("utf-8"),
            file_name="influencer_scheme_qualifiers.csv",
            mime="text/csv",
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

    # Attach each influencer's qualified gift (by cumulative Name + Phone total).
    gift_lookup = qualifiers(base_df)[["Influencer", "Phone", "Gift"]]
    fdf = fdf.merge(gift_lookup, on=["Influencer", "Phone"], how="left")
    fdf["Gift"] = fdf["Gift"].fillna("Not qualified")

    show_cols = [
        "Purchase_Date",
        "Month_Label",
        "Distributor",
        "Influencer",
        "Dealer",
        "Quantity_MT",
        "Gift",
        "Verification_Status",
        "Phone",
    ]
    # Hide sensitive columns from influencers (phone numbers / SF IDs).
    if is_influencer:
        show_cols = [c for c in show_cols if c not in {"Phone", "Influencer"}]
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
