import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path
import re
from datetime import datetime, date

st.set_page_config(
    page_title="SQDB 30-60-90-120 Tracker",
    page_icon="📡",
    layout="wide",
)

FOLDER = Path(__file__).parent
TODAY = date(2026, 4, 9)

# ── helpers ────────────────────────────────────────────────────────────────

def phase_label(month_ts):
    """Return 30 / 60 / 90 / 120 / Beyond label relative to TODAY."""
    m = pd.Timestamp(month_ts)
    current = pd.Timestamp(TODAY.replace(day=1))
    diff = (m.year - current.year) * 12 + (m.month - current.month)
    if diff == 0:
        return "30-Day"
    elif diff == 1:
        return "60-Day"
    elif diff == 2:
        return "90-Day"
    elif diff == 3:
        return "120-Day"
    else:
        return "Beyond"

@st.cache_data(show_spinner="Loading on-air dates…")
def load_onair_dates():
    path = Path(r"C:\Users\v296938\Desktop\04202026 FWA CBAND Capacity_Full Data.xlsx")
    if not path.exists():
        return pd.DataFrame(columns=["Fuze Site ID", "On Air Date"])
    odf = pd.read_excel(path, usecols=["Fuze Site ID", "On Air Date"], engine="openpyxl")
    odf["On Air Date"] = pd.to_datetime(odf["On Air Date"], errors="coerce")
    return odf.dropna(subset=["Fuze Site ID"]).groupby("Fuze Site ID")["On Air Date"].min().reset_index()

@st.cache_data(show_spinner="Loading weekly files…")
def load_all_files():
    pattern = re.compile(r"FWA_CBAND_Forecast_Sites_(\d{8})")
    records = []
    all_files = sorted(
        list(FOLDER.glob("**/FWA_CBAND_Forecast_Sites_*.xlsx")) +
        list(FOLDER.glob("**/FWA_CBAND_Forecast_Sites_*.csv"))
    )
    for f in all_files:
        m = pattern.search(f.stem)
        if not m:
            continue
        snap_date = pd.to_datetime(m.group(1), format="%Y%m%d").date()
        if snap_date.year not in (2025, 2026):
            continue
        try:
            if f.suffix.lower() == ".csv":
                df = pd.read_csv(f)
            else:
                df = pd.read_excel(f, engine="openpyxl")
            if "Fuze Site ID" not in df.columns:
                continue
            df["Snapshot"] = snap_date
            # For 2025 snapshot files, keep only rows with 2026 Forecast Month
            if snap_date.year == 2025:
                df["Forecast Month"] = pd.to_datetime(df["Forecast Month"])
                df = df[df["Forecast Month"].dt.year == 2026]
                if df.empty:
                    continue
            records.append(df)
        except Exception:
            pass
    if not records:
        return pd.DataFrame()
    all_df = pd.concat(records, ignore_index=True)
    all_df["Forecast Month"] = pd.to_datetime(all_df["Forecast Month"])
    all_df["Phase"] = all_df["Forecast Month"].apply(phase_label)
    return all_df

# ── load ───────────────────────────────────────────────────────────────────

all_df = load_all_files()

if all_df.empty:
    st.error("No forecast files found in this folder.")
    st.stop()

snapshots_available = sorted(all_df["Snapshot"].unique())
latest_snap = max(snapshots_available)
markets_available = sorted(all_df["Market"].dropna().unique())

# ── sidebar ────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("📡 SQDB Tracker")
    st.caption("FWA C-Band Forecast — OFS Sites")
    st.divider()

    selected_markets = st.multiselect(
        "Filter by Market",
        options=markets_available,
        default=[],
        placeholder="All markets",
    )

    num_weeks = st.slider("Weeks of history to show", min_value=4, max_value=len(snapshots_available), value=min(12, len(snapshots_available)))
    recent_snaps = snapshots_available[-num_weeks:]

    st.divider()
    st.caption(f"Latest snapshot: **{latest_snap}**")
    st.caption(f"Total weekly files: **{len(snapshots_available)}**")

# ── filter ────────────────────────────────────────────────────────────────

df = all_df.copy()
if selected_markets:
    df = df[df["Market"].isin(selected_markets)]

latest_df = df[df["Snapshot"] == latest_snap]
recent_df = df[df["Snapshot"].isin(recent_snaps)]

# ── page title ────────────────────────────────────────────────────────────

st.title("SQDB 30-60-90-120 Schedule Tracker")
st.caption(f"FWA C-Band · As of {latest_snap} · Today: {TODAY}")

PHASES = ["30-Day", "60-Day", "90-Day", "120-Day"]
PHASE_COLORS = {"30-Day": "#0d6efd", "60-Day": "#198754", "90-Day": "#fd7e14", "120-Day": "#6f42c1"}

# ── KPI cards (latest snapshot) ───────────────────────────────────────────

st.subheader("Current Forecast Snapshot")

phase_summary = (
    latest_df[latest_df["Phase"].isin(PHASES)]
    .groupby("Phase")
    .agg(Sites=("Fuze Site ID", "nunique"), VCG_OFS=("VCG-OFS", "sum"), VBG_OFS=("VBG-OFS", "sum"))
    .reindex(PHASES)
    .fillna(0)
    .astype({"Sites": int, "VCG_OFS": int, "VBG_OFS": int})
    .reset_index()
)

cols = st.columns(4)
for col, (_, row) in zip(cols, phase_summary.iterrows()):
    with col:
        color = PHASE_COLORS[row["Phase"]]
        st.markdown(
            f"""
            <div style="border-left: 5px solid {color}; padding: 12px 16px; background: #f8f9fa; border-radius: 4px;">
                <div style="font-size:1.1rem; font-weight:700; color:{color}">{row['Phase']}</div>
                <div style="font-size:2rem; font-weight:800; margin:4px 0">{row['Sites']:,}</div>
                <div style="font-size:0.8rem; color:#555">Sites</div>
                <div style="margin-top:8px; font-size:0.85rem">
                    VCG-OFS: <b>{row['VCG_OFS']:,}</b><br>
                    VBG-OFS: <b>{row['VBG_OFS']:,}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.divider()

# ── tabs ──────────────────────────────────────────────────────────────────

tab_trend, tab_cumulative, tab_compare, tab_adherence, tab_market, tab_detail, tab_map = st.tabs(["Week-over-Week Trend", "Cumulative OFS", "Snapshot Comparison", "Schedule Adherence", "Market Breakdown", "Site Detail", "Site Map"])

# ── TREND TAB ─────────────────────────────────────────────────────────────
with tab_trend:
    trend_df = (
        recent_df[recent_df["Phase"].isin(PHASES)]
        .groupby(["Snapshot", "Phase"])
        .agg(Sites=("Fuze Site ID", "nunique"), VCG_OFS=("VCG-OFS", "sum"), VBG_OFS=("VBG-OFS", "sum"))
        .reset_index()
    )

    metric = st.radio("Metric", ["Sites", "VCG-OFS", "VBG-OFS"], horizontal=True)
    col_map = {"Sites": "Sites", "VCG-OFS": "VCG_OFS", "VBG-OFS": "VBG_OFS"}
    y_col = col_map[metric]

    fig = go.Figure()
    for phase in PHASES:
        phase_data = trend_df[trend_df["Phase"] == phase].sort_values("Snapshot")
        fig.add_trace(go.Scatter(
            x=phase_data["Snapshot"],
            y=phase_data[y_col],
            name=phase,
            mode="lines+markers",
            line=dict(color=PHASE_COLORS[phase], width=2),
            marker=dict(size=6),
            hovertemplate=f"<b>{phase}</b><br>Week: %{{x}}<br>{metric}: %{{y:,}}<extra></extra>",
        ))

    fig.update_layout(
        title=f"{metric} by Phase — Week-over-Week",
        xaxis_title="Snapshot Week",
        yaxis_title=metric,
        hovermode="x unified",
        height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=60, b=40),
    )
    st.plotly_chart(fig, width="stretch")

    # WoW delta table
    st.subheader("Week-over-Week Delta (latest vs prior week)")
    if len(snapshots_available) >= 2:
        prev_snap = snapshots_available[-2]
        prev_df_f = df[df["Snapshot"] == prev_snap]
        curr_summary = (
            latest_df[latest_df["Phase"].isin(PHASES)]
            .groupby("Phase")
            .agg(Sites_now=("Fuze Site ID", "nunique"), VCG_now=("VCG-OFS", "sum"), VBG_now=("VBG-OFS", "sum"))
        )
        prev_summary = (
            prev_df_f[prev_df_f["Phase"].isin(PHASES)]
            .groupby("Phase")
            .agg(Sites_prev=("Fuze Site ID", "nunique"), VCG_prev=("VCG-OFS", "sum"), VBG_prev=("VBG-OFS", "sum"))
        )
        delta = curr_summary.join(prev_summary).reindex(PHASES).fillna(0).astype(int)
        delta["Δ Sites"] = delta["Sites_now"] - delta["Sites_prev"]
        delta["Δ VCG-OFS"] = delta["VCG_now"] - delta["VCG_prev"]
        delta["Δ VBG-OFS"] = delta["VBG_now"] - delta["VBG_prev"]
        display_delta = delta[["Sites_now", "Sites_prev", "Δ Sites", "VCG_now", "VCG_prev", "Δ VCG-OFS", "VBG_now", "VBG_prev", "Δ VBG-OFS"]].rename(columns={
            "Sites_now": f"Sites ({latest_snap})",
            "Sites_prev": f"Sites ({prev_snap})",
            "VCG_now": f"VCG ({latest_snap})",
            "VCG_prev": f"VCG ({prev_snap})",
            "VBG_now": f"VBG ({latest_snap})",
            "VBG_prev": f"VBG ({prev_snap})",
        })

        def color_delta(val):
            if isinstance(val, (int, float)):
                if val > 0:
                    return "color: green"
                elif val < 0:
                    return "color: red"
            return ""

        st.dataframe(
            display_delta.style.map(color_delta, subset=["Δ Sites", "Δ VCG-OFS", "Δ VBG-OFS"]),
            width="stretch",
        )

# ── CUMULATIVE TAB ────────────────────────────────────────────────────────
with tab_cumulative:
    st.subheader("Cumulative OFS by Forecast Date")
    st.caption("Running total of addresses from the latest snapshot, ordered by site forecast date.")

    cum_metric = st.radio("Metric", ["VCG-OFS", "VBG-OFS", "Both"], horizontal=True, key="cum_metric")

    # Daily totals from latest snapshot, within 30/60/90 phases only
    daily = (
        latest_df[latest_df["Phase"].isin(PHASES)]
        .groupby("Forecast Date")
        .agg(VCG=("VCG-OFS", "sum"), VBG=("VBG-OFS", "sum"), Sites=("Fuze Site ID", "nunique"))
        .reset_index()
        .sort_values("Forecast Date")
    )
    daily["Cum VCG-OFS"] = daily["VCG"].cumsum()
    daily["Cum VBG-OFS"] = daily["VBG"].cumsum()
    daily["Cum Sites"] = daily["Sites"].cumsum()

    # Phase boundary lines
    phase_bounds = (
        latest_df[latest_df["Phase"].isin(PHASES)]
        .groupby("Phase")["Forecast Date"]
        .max()
        .reindex(PHASES)
    )

    fig_cum = go.Figure()

    if cum_metric in ("VCG-OFS", "Both"):
        fig_cum.add_trace(go.Scatter(
            x=daily["Forecast Date"],
            y=daily["Cum VCG-OFS"],
            name="Cumulative VCG-OFS",
            mode="lines",
            line=dict(color="#0d6efd", width=2),
            fill="tozeroy",
            fillcolor="rgba(13,110,253,0.08)",
            hovertemplate="Date: %{x}<br>Cum VCG-OFS: %{y:,}<extra></extra>",
        ))

    if cum_metric in ("VBG-OFS", "Both"):
        fig_cum.add_trace(go.Scatter(
            x=daily["Forecast Date"],
            y=daily["Cum VBG-OFS"],
            name="Cumulative VBG-OFS",
            mode="lines",
            line=dict(color="#fd7e14", width=2),
            fill="tozeroy",
            fillcolor="rgba(253,126,20,0.08)",
            hovertemplate="Date: %{x}<br>Cum VBG-OFS: %{y:,}<extra></extra>",
        ))

    # Vertical phase boundary lines (add as shapes + annotations manually)
    for phase, color in PHASE_COLORS.items():
        bound = phase_bounds.get(phase)
        if pd.notna(bound):
            x_ts = pd.Timestamp(bound).timestamp() * 1000  # ms epoch for plotly
            fig_cum.add_shape(
                type="line",
                xref="x", yref="paper",
                x0=x_ts, x1=x_ts, y0=0, y1=1,
                line=dict(color=color, dash="dash", width=1.5),
            )
            fig_cum.add_annotation(
                x=x_ts, yref="paper", y=1.02,
                text=phase, showarrow=False,
                font=dict(color=color, size=12),
                xanchor="center",
            )

    fig_cum.update_layout(
        xaxis_title="Forecast Date",
        yaxis_title="Cumulative OFS Addresses",
        hovermode="x unified",
        height=450,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=60, b=40),
    )
    st.plotly_chart(fig_cum, width="stretch")

    # Cumulative milestones at each phase boundary
    st.subheader("Cumulative Totals at Phase Boundaries")
    rows = []
    for phase in PHASES:
        bound = phase_bounds.get(phase)
        if pd.isna(bound):
            continue
        snap = daily[daily["Forecast Date"] <= bound]
        if snap.empty:
            continue
        last = snap.iloc[-1]
        rows.append({
            "Phase": phase,
            "Through Date": bound.date() if hasattr(bound, "date") else bound,
            "Cum Sites": int(last["Cum Sites"]),
            "Cum VCG-OFS": int(last["Cum VCG-OFS"]),
            "Cum VBG-OFS": int(last["Cum VBG-OFS"]),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


# ── SNAPSHOT COMPARISON TAB ───────────────────────────────────────────────
with tab_compare:
    st.subheader("Snapshot Comparison")

    snap_options = [str(s) for s in snapshots_available]
    col_a, col_b = st.columns(2)
    with col_a:
        snap_a = st.selectbox("Snapshot A (baseline)", snap_options, index=max(0, len(snap_options) - 2), key="snap_a")
    with col_b:
        snap_b = st.selectbox("Snapshot B (compare)", snap_options, index=len(snap_options) - 1, key="snap_b")

    cmp_markets = st.multiselect("Filter by Market", options=markets_available, default=[], placeholder="All markets", key="cmp_markets")
    cmp_metric = st.radio("Metric", ["Sites", "VCG-OFS", "VBG-OFS"], horizontal=True, key="cmp_metric")
    cmp_col = {"Sites": ("Fuze Site ID", "nunique"), "VCG-OFS": ("VCG-OFS", "sum"), "VBG-OFS": ("VBG-OFS", "sum")}

    def snap_summary(snap_str, group_col=None):
        snap_date = pd.to_datetime(snap_str).date()
        sdf = df[(df["Snapshot"] == snap_date) & (df["Phase"].isin(PHASES))]
        if cmp_markets:
            sdf = sdf[sdf["Market"].isin(cmp_markets)]
        gb = [group_col, "Phase"] if group_col else ["Phase"]
        agg_col, agg_fn = cmp_col[cmp_metric]
        return sdf.groupby(gb)[agg_col].agg(agg_fn).rename(cmp_metric).reset_index()

    sum_a = snap_summary(snap_a)
    sum_b = snap_summary(snap_b)

    # ── Grouped bar chart by phase ─────────────────────────────────────────
    fig_cmp = go.Figure()
    for label, sdata, pattern in [(snap_a, sum_a, ""), (snap_b, sum_b, "/")]:
        fig_cmp.add_trace(go.Bar(
            name=label,
            x=sdata["Phase"],
            y=sdata[cmp_metric],
            text=sdata[cmp_metric].apply(lambda v: f"{v:,}"),
            textposition="outside",
            marker_pattern_shape=pattern,
        ))

    fig_cmp.update_layout(
        barmode="group",
        title=f"{cmp_metric} by Phase — {snap_a} vs {snap_b}",
        xaxis_title="Phase",
        yaxis_title=cmp_metric,
        height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=60, b=40),
    )
    st.plotly_chart(fig_cmp, width="stretch")

    # ── Delta summary table ────────────────────────────────────────────────
    st.subheader(f"Delta: {snap_b} vs {snap_a}")
    merged = sum_a.merge(sum_b, on="Phase", suffixes=(" A", " B")).set_index("Phase").reindex(PHASES)
    merged["Δ"] = merged[f"{cmp_metric} B"] - merged[f"{cmp_metric} A"]
    merged["Δ %"] = (merged["Δ"] / merged[f"{cmp_metric} A"].replace(0, float("nan")) * 100).round(1)
    merged = merged.rename(columns={f"{cmp_metric} A": snap_a, f"{cmp_metric} B": snap_b}).fillna(0).astype({snap_a: int, snap_b: int, "Δ": int})

    def style_delta(val):
        if isinstance(val, (int, float)):
            if val > 0: return "color: green; font-weight: bold"
            if val < 0: return "color: red; font-weight: bold"
        return ""

    st.dataframe(merged.style.map(style_delta, subset=["Δ", "Δ %"]), width="stretch")

    # ── Market-level comparison ────────────────────────────────────────────
    with st.expander("Market-level breakdown"):
        sum_a_mkt = snap_summary(snap_a, "Market")
        sum_b_mkt = snap_summary(snap_b, "Market")
        mkt_merged = sum_a_mkt.merge(sum_b_mkt, on=["Market", "Phase"], suffixes=(" A", " B"))
        mkt_merged["Δ"] = mkt_merged[f"{cmp_metric} B"] - mkt_merged[f"{cmp_metric} A"]

        pivot_delta = mkt_merged.pivot_table(index="Market", columns="Phase", values="Δ", fill_value=0).reindex(columns=PHASES, fill_value=0)
        pivot_delta["Total Δ"] = pivot_delta.sum(axis=1)
        pivot_delta = pivot_delta.sort_values("Total Δ")

        fig_mkt_cmp = go.Figure()
        for phase in PHASES:
            fig_mkt_cmp.add_trace(go.Bar(
                name=phase,
                y=pivot_delta.index,
                x=pivot_delta[phase],
                orientation="h",
                marker_color=PHASE_COLORS[phase],
            ))
        fig_mkt_cmp.update_layout(
            barmode="relative",
            title=f"{cmp_metric} Delta by Market ({snap_a} → {snap_b})",
            height=max(500, len(pivot_delta) * 20),
            xaxis_title=f"Δ {cmp_metric}",
            margin=dict(l=130, t=60, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
        )
        st.plotly_chart(fig_mkt_cmp, width="stretch")


# ── SCHEDULE ADHERENCE TAB ────────────────────────────────────────────────
with tab_adherence:
    st.subheader("Schedule Adherence")
    st.caption(
        "Compares each site's forecasted month in a baseline snapshot against a later snapshot. "
        "**On Schedule** = same or earlier month. **Slipped** = moved to a later month. "
        "**Completed** = no longer on report, has On Air Date. **Dropped** = no longer on report, no On Air Date."
    )

    adh_col1, adh_col2 = st.columns(2)
    valid_snaps = [str(s) for s in snapshots_available]
    with adh_col1:
        base_snap = st.selectbox("Baseline snapshot", valid_snaps, index=0, key="adh_base")
    with adh_col2:
        comp_snap = st.selectbox("Compare snapshot", valid_snaps, index=len(valid_snaps) - 1, key="adh_comp")

    adh_col3, adh_col4, adh_col5 = st.columns(3)
    with adh_col3:
        adh_markets = st.multiselect("Filter by Market", options=markets_available, default=[], placeholder="All markets", key="adh_markets")
    with adh_col4:
        sub_market_options = sorted(df["Sub Market"].dropna().unique()) if not adh_markets else sorted(df[df["Market"].isin(adh_markets)]["Sub Market"].dropna().unique())
        adh_submarkets = st.multiselect("Filter by Sub Market", options=sub_market_options, default=[], placeholder="All sub markets", key="adh_submarkets")
    with adh_col5:
        adh_phases = st.multiselect("Filter by Phase (baseline)", options=PHASES, default=[], placeholder="All phases", key="adh_phases")

    base_date = pd.to_datetime(base_snap).date()
    comp_date = pd.to_datetime(comp_snap).date()

    comp_raw = df[df["Snapshot"] == comp_date].copy()

    # Universe: all sites ever seen across all snapshots
    # Base month = forecast month from baseline snapshot if present, else earliest ever seen
    base_fm_snap = (
        df[df["Snapshot"] == base_date]
        .groupby("Fuze Site ID")
        .agg(Base_Month_Snap=("Forecast Month", "min"))
        .reset_index()
    )
    universe = (
        df.groupby("Fuze Site ID")
        .agg(Base_Month_Early=("Forecast Month", "min"),
             Market=("Market", "first"), Sub_Market=("Sub Market", "first"),
             VCG=("VCG-OFS", "sum"), VBG=("VBG-OFS", "sum"))
        .reset_index()
    )
    base_sites = universe.merge(base_fm_snap, on="Fuze Site ID", how="left")
    base_sites["Base_Month"] = pd.to_datetime(
        base_sites["Base_Month_Snap"].combine_first(base_sites["Base_Month_Early"])
    )
    base_sites = base_sites.drop(columns=["Base_Month_Snap", "Base_Month_Early"])

    # Apply market / submarket / phase filters to universe
    if adh_markets:
        base_sites = base_sites[base_sites["Market"].isin(adh_markets)]
        comp_raw   = comp_raw[comp_raw["Market"].isin(adh_markets)]
    if adh_submarkets:
        base_sites = base_sites[base_sites["Sub Market"].isin(adh_submarkets)]
        comp_raw   = comp_raw[comp_raw["Sub Market"].isin(adh_submarkets)]
    if adh_phases:
        base_sites["_Phase"] = base_sites["Base_Month"].apply(phase_label)
        base_sites = base_sites[base_sites["_Phase"].isin(adh_phases)].drop(columns=["_Phase"])

    comp_sites = (
        comp_raw.groupby("Fuze Site ID")
        .agg(Comp_Month=("Forecast Month", "min"))
        .reset_index()
    )
    comp_sites["Comp_Month"] = pd.to_datetime(comp_sites["Comp_Month"])

    merged = base_sites.merge(comp_sites, on="Fuze Site ID", how="left")

    onair_df = load_onair_dates()
    onair_ids = set(onair_df["Fuze Site ID"].dropna().astype(str))
    onair_date_map = dict(zip(onair_df["Fuze Site ID"].astype(str), onair_df["On Air Date"]))
    comp_snap_month = pd.Timestamp(comp_date).to_period("M").to_timestamp()

    def classify(row):
        if pd.isna(row["Comp_Month"]):
            oa = onair_date_map.get(str(row["Fuze Site ID"]))
            return "Completed" if (oa is not None and pd.notna(oa) and oa <= pd.Timestamp(comp_date)) else "Dropped"
        if row["Comp_Month"] < comp_snap_month:
            return "Slipped"  # Past due — still on report but forecast month already passed
        if row["Comp_Month"] <= row["Base_Month"]:
            return "On Schedule"
        return "Slipped"

    merged["Status"] = merged.apply(classify, axis=1)
    merged["Months Slipped"] = (
        (merged["Comp_Month"].dt.year - merged["Base_Month"].dt.year) * 12 +
        (merged["Comp_Month"].dt.month - merged["Base_Month"].dt.month)
    ).clip(lower=0)

    # ── KPI row ───────────────────────────────────────────────────────────
    status_counts = merged["Status"].value_counts()
    total     = len(merged)
    on_sched  = status_counts.get("On Schedule", 0)
    slipped   = status_counts.get("Slipped", 0)
    completed = status_counts.get("Completed", 0)
    dropped   = status_counts.get("Dropped", 0)

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Sites (baseline)", f"{total:,}")
    pct = lambda n: f"{n/total*100:.1f}%" if total else "—"
    k2.metric("On Schedule", f"{on_sched:,}", pct(on_sched))
    k3.metric("Slipped", f"{slipped:,}", f"-{pct(slipped)}" if slipped else "0%", delta_color="inverse")
    k4.metric("Completed", f"{completed:,}", pct(completed))
    k5.metric("Dropped", f"{dropped:,}", f"-{pct(dropped)}" if dropped else "0%", delta_color="inverse")

    st.divider()

    # ── Week-over-week trend ──────────────────────────────────────────────
    trend_snaps = [s for s in snapshots_available if s >= base_date]
    trend_rows = []
    for snap in trend_snaps:
        snap_raw = df[df["Snapshot"] == snap].groupby("Fuze Site ID").agg(Comp_Month=("Forecast Month", "min")).reset_index()
        snap_raw["Comp_Month"] = pd.to_datetime(snap_raw["Comp_Month"])
        snap_merged = base_sites.merge(snap_raw, on="Fuze Site ID", how="left")
        snap_month = pd.Timestamp(snap).to_period("M").to_timestamp()
        def _classify(row, _sm=snap_month):
            if pd.isna(row["Comp_Month"]):
                oa = onair_date_map.get(str(row["Fuze Site ID"]))
                return "Completed" if (oa is not None and pd.notna(oa) and oa <= _sm) else "Dropped"
            if row["Comp_Month"] < _sm:
                return "Slipped"
            return "On Schedule" if row["Comp_Month"] <= row["Base_Month"] else "Slipped"
        snap_merged["Status"] = snap_merged.apply(_classify, axis=1)
        sc = snap_merged["Status"].value_counts()
        trend_rows.append({"Snapshot": snap, "On Schedule": sc.get("On Schedule", 0),
                            "Slipped": sc.get("Slipped", 0), "Completed": sc.get("Completed", 0),
                            "Dropped": sc.get("Dropped", 0)})
    trend_df = pd.DataFrame(trend_rows)

    STATUS_COLORS_TREND = {"On Schedule": "#198754", "Slipped": "#dc3545", "Completed": "#fd7e14", "Dropped": "#6c757d"}
    fig_trend = go.Figure()
    for status, color in STATUS_COLORS_TREND.items():
        fig_trend.add_trace(go.Scatter(
            x=trend_df["Snapshot"], y=trend_df[status],
            name=status, mode="lines+markers",
            line=dict(color=color, width=2), marker=dict(size=6),
            hovertemplate=f"<b>{status}</b><br>%{{x}}<br>Sites: %{{y:,}}<extra></extra>",
        ))
    fig_trend.update_layout(
        title="Status Trend (Baseline → Each Snapshot)",
        xaxis_title="Snapshot", yaxis_title="Sites",
        height=320, margin=dict(t=50, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig_trend, width="stretch")

    st.divider()

    left, right = st.columns(2)

    # ── Donut chart ───────────────────────────────────────────────────────
    with left:
        STATUS_COLORS = {"On Schedule": "#198754", "Slipped": "#dc3545", "Completed": "#dc3545", "Dropped": "#6c757d"}
        labels = list(status_counts.index)
        values = list(status_counts.values)
        colors = [STATUS_COLORS.get(l, "#aaa") for l in labels]
        fig_donut = go.Figure(go.Pie(
            labels=labels, values=values,
            hole=0.5,
            marker_colors=colors,
            textinfo="label+percent",
            hovertemplate="%{label}: %{value:,} sites<extra></extra>",
        ))
        fig_donut.update_layout(title="Schedule Status", height=350, margin=dict(t=50, b=20))
        st.plotly_chart(fig_donut, width="stretch")

    # ── Slippage distribution ─────────────────────────────────────────────
    with right:
        slip_df = merged[merged["Status"] == "Slipped"]
        if not slip_df.empty:
            slip_dist = slip_df["Months Slipped"].value_counts().sort_index().reset_index()
            slip_dist.columns = ["Months Slipped", "Sites"]
            fig_slip = go.Figure(go.Bar(
                x=slip_dist["Months Slipped"].astype(str) + "mo",
                y=slip_dist["Sites"],
                marker_color="#dc3545",
                text=slip_dist["Sites"],
                textposition="outside",
                hovertemplate="Slipped %{x}: %{y:,} sites<extra></extra>",
            ))
            fig_slip.update_layout(
                title="Slippage Distribution",
                xaxis_title="Months Slipped",
                yaxis_title="Sites",
                height=350,
                margin=dict(t=50, b=40),
            )
            st.plotly_chart(fig_slip, width="stretch")
        else:
            st.info("No slipped sites in this comparison.")

    # ── Market adherence breakdown ────────────────────────────────────────
    st.subheader("Market Breakdown")
    mkt_adh = (
        merged.groupby(["Market", "Status"])
        .size()
        .reset_index(name="Sites")
        .pivot_table(index="Market", columns="Status", values="Sites", fill_value=0)
    )
    for col in ["On Schedule", "Slipped", "Completed", "Dropped"]:
        if col not in mkt_adh.columns:
            mkt_adh[col] = 0
    mkt_adh = mkt_adh[["On Schedule", "Slipped", "Completed", "Dropped"]]
    mkt_adh["Total"] = mkt_adh.sum(axis=1)
    mkt_adh["On Schedule %"] = (mkt_adh["On Schedule"] / mkt_adh["Total"].replace(0, float("nan")) * 100).round(1).fillna(0)
    mkt_adh = mkt_adh.sort_values("On Schedule %", ascending=True)

    fig_mkt_adh = go.Figure()
    for status, color in STATUS_COLORS.items():
        if status in mkt_adh.columns:
            fig_mkt_adh.add_trace(go.Bar(
                name=status,
                y=mkt_adh.index,
                x=mkt_adh[status],
                orientation="h",
                marker_color=color,
                hovertemplate=f"{status}: %{{x:,}}<extra></extra>",
            ))
    fig_mkt_adh.update_layout(
        barmode="stack",
        title="Sites by Status per Market",
        height=max(500, len(mkt_adh) * 20),
        margin=dict(l=130, t=60, b=40),
        xaxis_title="Sites",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
    )
    st.plotly_chart(fig_mkt_adh, width="stretch")

    # ── Site detail ───────────────────────────────────────────────────────
    with st.expander("Site-level detail"):
        status_filter = st.selectbox("Status filter", ["All", "On Schedule", "Slipped", "Completed", "Dropped"], key="adh_status")
        detail_df = merged.copy()
        if status_filter != "All":
            detail_df = detail_df[detail_df["Status"] == status_filter]
        detail_df = detail_df.sort_values(["Status", "Market", "Months Slipped"], ascending=[True, True, False])
        display_df = (
            detail_df[["Fuze Site ID", "Market", "Sub_Market", "Status", "Base_Month", "Comp_Month", "Months Slipped", "VCG", "VBG"]]
            .rename(columns={"Sub_Market": "Sub Market", "Base_Month": f"Forecast ({base_snap})", "Comp_Month": f"Forecast ({comp_snap})", "VCG": "VCG-OFS", "VBG": "VBG-OFS"})
            .reset_index(drop=True)
        )
        adh_sel = st.dataframe(
            display_df,
            width="stretch",
            hide_index=True,
            selection_mode="single-row",
            on_select="rerun",
            key="adh_detail_sel",
        )
        rows_sel = adh_sel.selection.rows
        if rows_sel:
            clicked_id = str(int(display_df.iloc[rows_sel[0]]["Fuze Site ID"]))
            st.session_state["_hist_prefill"] = clicked_id
            st.toast(f"Site {clicked_id} selected — open the Site Detail tab to view history")
        st.caption(f"{len(detail_df):,} sites — click any row to load its history in the Site Detail tab")


# ── MARKET TAB ────────────────────────────────────────────────────────────
with tab_market:
    market_phase = (
        latest_df[latest_df["Phase"].isin(PHASES)]
        .groupby(["Market", "Phase"])
        .agg(Sites=("Fuze Site ID", "nunique"), VCG_OFS=("VCG-OFS", "sum"))
        .reset_index()
    )

    metric_m = st.radio("Metric ", ["Sites", "VCG-OFS"], horizontal=True, key="mkt_metric")
    y_col_m = "Sites" if metric_m == "Sites" else "VCG_OFS"

    # Pivot for sorted bar chart
    pivot = market_phase.pivot_table(index="Market", columns="Phase", values=y_col_m, fill_value=0).reindex(columns=PHASES, fill_value=0)
    pivot["Total"] = pivot.sum(axis=1)
    pivot = pivot.sort_values("Total", ascending=True).drop(columns="Total")

    fig_m = go.Figure()
    for phase in PHASES:
        fig_m.add_trace(go.Bar(
            name=phase,
            y=pivot.index,
            x=pivot[phase],
            orientation="h",
            marker_color=PHASE_COLORS[phase],
        ))
    fig_m.update_layout(
        barmode="stack",
        title=f"{metric_m} by Market and Phase",
        height=max(500, len(pivot) * 20),
        margin=dict(l=130, t=60, b=40),
        xaxis_title=metric_m,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
    )
    st.plotly_chart(fig_m, width="stretch")

    # Market summary table
    market_table = (
        latest_df[latest_df["Phase"].isin(PHASES)]
        .groupby("Market")
        .agg(
            Total_Sites=("Fuze Site ID", "nunique"),
            VCG_OFS=("VCG-OFS", "sum"),
            VBG_OFS=("VBG-OFS", "sum"),
        )
        .sort_values("Total_Sites", ascending=False)
        .reset_index()
    )
    st.dataframe(market_table, width="stretch", hide_index=True)

# ── DETAIL TAB ────────────────────────────────────────────────────────────
with tab_detail:
    st.subheader("Site-Level Detail")

    # ── Compute Status (On Schedule / Slipped) using earliest snap as baseline ──
    earliest_snap = min(snapshots_available)
    _base_fm_snap = (
        df[df["Snapshot"] == earliest_snap]
        .groupby("Fuze Site ID")
        .agg(Base_Month_Snap=("Forecast Month", "min"))
        .reset_index()
    )
    _earliest_fm = (
        df.groupby("Fuze Site ID")
        .agg(Base_Month_Early=("Forecast Month", "min"))
        .reset_index()
    )
    _base_lookup = _base_fm_snap.merge(_earliest_fm, on="Fuze Site ID", how="right")
    _base_lookup["Base_Month"] = pd.to_datetime(
        _base_lookup["Base_Month_Snap"].combine_first(_base_lookup["Base_Month_Early"])
    )
    _base_lookup = _base_lookup[["Fuze Site ID", "Base_Month"]]

    _det_onair_ids = set(load_onair_dates()["Fuze Site ID"].dropna().astype(str))
    _latest_snap_month = pd.Timestamp(latest_snap).to_period("M").to_timestamp()

    det_df = latest_df[latest_df["Phase"].isin(PHASES)].copy()
    det_df = det_df.merge(_base_lookup, on="Fuze Site ID", how="left")
    det_df["_Comp_Month"] = pd.to_datetime(det_df["Forecast Month"])

    def _classify_detail(row):
        if pd.isna(row["_Comp_Month"]):
            return "Completed" if str(row["Fuze Site ID"]) in _det_onair_ids else "Dropped"
        if row["_Comp_Month"] < _latest_snap_month:
            return "Slipped"
        if row["_Comp_Month"] <= row["Base_Month"]:
            return "On Schedule"
        return "Slipped"

    det_df["Status"] = det_df.apply(_classify_detail, axis=1)

    # ── Site History Search ───────────────────────────────────────────────
    st.markdown("### Site History")
    _prefill = st.session_state.get("_hist_prefill", "")
    if _prefill:
        st.session_state["site_hist_input"] = _prefill
        del st.session_state["_hist_prefill"]
    site_id_input = st.text_input("Search Fuze Site ID", placeholder="e.g. 12345", key="site_hist_input")

    if site_id_input.strip():
        site_hist = all_df[all_df["Fuze Site ID"].astype(str) == site_id_input.strip()].copy()

        if site_hist.empty:
            st.warning(f"No data found for Fuze Site ID: {site_id_input.strip()}")
        else:
            site_hist["Forecast Month"] = pd.to_datetime(site_hist["Forecast Month"])
            base_fm = site_hist["Forecast Month"].min()
            first_snap = site_hist["Snapshot"].min()

            # On Air Date lookup
            _odf = load_onair_dates()
            _orow = _odf[_odf["Fuze Site ID"].astype(str) == site_id_input.strip()]
            on_air_date = _orow["On Air Date"].iloc[0] if not _orow.empty else None

            # Metadata from first appearance
            _first = site_hist.sort_values("Snapshot").iloc[0]
            _market = _first["Market"] if "Market" in site_hist.columns else "—"
            _submarket = _first["Sub Market"] if "Sub Market" in site_hist.columns else "—"

            # KPI row
            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("Market", _market)
            k2.metric("Sub Market", _submarket)
            k3.metric("First Snapshot", str(first_snap))
            k4.metric("Original FM", base_fm.strftime("%b %Y") if pd.notna(base_fm) else "—")
            k5.metric("On Air Date", on_air_date.strftime("%Y-%m-%d") if pd.notna(on_air_date) else "—")

            # Build full history across all snapshots
            hist_rows = []
            for snap in snapshots_available:
                snap_month_ts = pd.Timestamp(snap).to_period("M").to_timestamp()
                snap_site = site_hist[site_hist["Snapshot"] == snap]
                if not snap_site.empty:
                    fm = snap_site["Forecast Month"].min()
                    phase = phase_label(fm)
                    vcg = int(snap_site["VCG-OFS"].sum()) if "VCG-OFS" in snap_site.columns else 0
                    vbg = int(snap_site["VBG-OFS"].sum()) if "VBG-OFS" in snap_site.columns else 0
                    if fm < snap_month_ts:
                        status = "Slipped"
                    elif fm <= base_fm:
                        status = "On Schedule"
                    else:
                        status = "Slipped"
                    hist_rows.append({"Snapshot": snap, "Forecast Month": fm.strftime("%b %Y"),
                                      "Phase": phase, "Status": status, "VCG-OFS": vcg, "VBG-OFS": vbg, "In Report": "✓"})
                elif snap > first_snap:
                    status = "Completed" if (pd.notna(on_air_date) and on_air_date.date() <= snap) else "Dropped"
                    hist_rows.append({"Snapshot": snap, "Forecast Month": "—",
                                      "Phase": "—", "Status": status, "VCG-OFS": "—", "VBG-OFS": "—", "In Report": "✗"})

            hist_df = pd.DataFrame(hist_rows)

            # Forecast month timeline chart
            chart_pts = site_hist.groupby("Snapshot")["Forecast Month"].min().reset_index()
            chart_pts["Forecast Month"] = pd.to_datetime(chart_pts["Forecast Month"])

            fig_hist = go.Figure()
            fig_hist.add_trace(go.Scatter(
                x=chart_pts["Snapshot"],
                y=chart_pts["Forecast Month"],
                mode="lines+markers",
                name="Forecast Month",
                line=dict(color="#0d6efd", width=2),
                marker=dict(size=8),
                hovertemplate="Snapshot: %{x}<br>Forecast Month: %{y|%b %Y}<extra></extra>",
            ))
            x_min = chart_pts["Snapshot"].min()
            x_max = chart_pts["Snapshot"].max()
            fig_hist.add_shape(type="line",
                x0=x_min, x1=x_max, y0=base_fm, y1=base_fm,
                line=dict(color="#6c757d", width=1, dash="dash"))
            fig_hist.add_annotation(
                x=x_min, y=base_fm, text="Original FM",
                showarrow=False, yshift=10, xanchor="left",
                font=dict(size=11, color="#6c757d"))
            fig_hist.update_layout(
                title=f"Forecast Month History — Site {site_id_input.strip()}",
                xaxis_title="Snapshot", yaxis_title="Forecast Month",
                yaxis=dict(tickformat="%b %Y"),
                height=320, margin=dict(t=50, b=40),
            )
            st.plotly_chart(fig_hist, width="stretch")

            # History table with color-coded status
            def _color_hist_status(val):
                c = {"On Schedule": "color: #198754", "Slipped": "color: #dc3545",
                     "Completed": "color: #fd7e14", "Dropped": "color: #6c757d"}
                return c.get(val, "")

            st.dataframe(
                hist_df.style.map(_color_hist_status, subset=["Status"]),
                width="stretch", hide_index=True,
            )
            st.caption(f"Site {site_id_input.strip()} · {site_hist['Snapshot'].nunique()} snapshots with active data")
            st.download_button(
                label="Export CSV",
                data=hist_df.to_csv(index=False).encode("utf-8"),
                file_name=f"site_{site_id_input.strip()}_history.csv",
                mime="text/csv",
            )

    st.divider()
    st.subheader("Browse All Sites")

    det_col1, det_col2 = st.columns(2)
    with det_col1:
        phase_filter = st.selectbox("Phase", ["All"] + PHASES)
    with det_col2:
        status_filter_det = st.selectbox("Status", ["All", "On Schedule", "Slipped"], key="det_status")

    filtered = det_df.copy()
    if phase_filter != "All":
        filtered = filtered[filtered["Phase"] == phase_filter]
    if status_filter_det != "All":
        filtered = filtered[filtered["Status"] == status_filter_det]

    filtered = filtered.sort_values(["Status", "Phase", "Market", "Forecast Date"])

    show_cols = ["Status", "Phase", "Market", "Sub Market", "Fuze Site ID", "CMA Name", "Zip Code", "Forecast Date", "VCG-OFS", "VBG-OFS"]
    show_cols = [c for c in show_cols if c in filtered.columns]
    st.dataframe(
        filtered[show_cols].reset_index(drop=True),
        width="stretch",
        hide_index=True,
    )
    st.caption(f"{len(filtered):,} rows")


# ── MAP TAB ───────────────────────────────────────────────────────────────
with tab_map:
    st.subheader("Site Map")
    st.caption(
        "Future build sites by phase (latest snapshot) and completed sites "
        "(present in prior snapshots but absent from the latest)."
    )

    mc1, mc2, mc3 = st.columns(3)
    with mc1:
        map_markets = st.multiselect("Market filter", markets_available, default=[], key="map_markets")
    with mc2:
        map_phases = st.multiselect("Future phases", PHASES, default=PHASES, key="map_phases")
    with mc3:
        map_show_completed = st.checkbox("Show completed sites", value=True, key="map_show_completed")

    # ── Future sites (latest snapshot) ────────────────────────────────────
    filt_latest = latest_df[latest_df["Phase"].isin(map_phases)].copy()
    if map_markets:
        filt_latest = filt_latest[filt_latest["Market"].isin(map_markets)]
    filt_latest = filt_latest.drop_duplicates("Fuze Site ID").copy()
    filt_latest["_Category"] = filt_latest["Phase"]
    filt_latest["_ForecastDate"] = pd.to_datetime(filt_latest["Forecast Date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("—")
    filt_latest["_VCG"] = filt_latest["VCG-OFS"].fillna(0).astype(int)
    filt_latest["_VBG"] = filt_latest["VBG-OFS"].fillna(0).astype(int)

    # ── Completed / Dropped sites (in history but not in latest) ──────────
    if map_show_completed:
        onair_df = load_onair_dates()
        latest_ids = set(latest_df["Fuze Site ID"].dropna().unique())
        hist = all_df[~all_df["Fuze Site ID"].isin(latest_ids)].copy()
        if map_markets:
            hist = hist[hist["Market"].isin(map_markets)]
        comp_sites = hist.sort_values("Snapshot", ascending=False).drop_duplicates("Fuze Site ID").copy()
        comp_sites = comp_sites.merge(onair_df[["Fuze Site ID", "On Air Date"]], on="Fuze Site ID", how="left")
        comp_sites["_Category"] = comp_sites["On Air Date"].apply(lambda d: "Completed" if pd.notna(d) and d.date() <= latest_snap else "Dropped")
        comp_sites["_ForecastDate"] = pd.to_datetime(comp_sites["Forecast Date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("—") if "Forecast Date" in comp_sites.columns else "—"
        comp_sites["_VCG"] = comp_sites["VCG-OFS"].fillna(0).astype(int) if "VCG-OFS" in comp_sites.columns else 0
        comp_sites["_VBG"] = comp_sites["VBG-OFS"].fillna(0).astype(int) if "VBG-OFS" in comp_sites.columns else 0
    else:
        comp_sites = pd.DataFrame()

    # ── Combine ────────────────────────────────────────────────────────────
    use_cols = ["Fuze Site ID", "Market", "Sub Market", "Site Latitude", "Site Longitude",
                "_Category", "_ForecastDate", "_VCG", "_VBG"]
    parts = []
    if not filt_latest.empty:
        parts.append(filt_latest[[c for c in use_cols if c in filt_latest.columns]])
    if not comp_sites.empty:
        parts.append(comp_sites[[c for c in use_cols if c in comp_sites.columns]])

    if not parts:
        st.info("No sites match the current filters.")
    else:
        map_df = pd.concat(parts, ignore_index=True)
        map_df["Site Latitude"] = pd.to_numeric(map_df["Site Latitude"], errors="coerce")
        map_df["Site Longitude"] = pd.to_numeric(map_df["Site Longitude"], errors="coerce")
        map_df = map_df.dropna(subset=["Site Latitude", "Site Longitude"])
        map_df = map_df[map_df["Site Latitude"].between(-90, 90) & map_df["Site Longitude"].between(-180, 180)]

        if map_df.empty:
            st.warning("No sites with valid coordinates found. Confirm 'Site Latitude' / 'Site Longitude' columns are populated.")
        else:
            MAP_COLORS = {"30-Day": "#0d6efd", "60-Day": "#198754", "90-Day": "#fd7e14", "120-Day": "#6f42c1", "Completed": "#dc3545", "Dropped": "#212529"}
            categories = map_phases + (["Completed", "Dropped"] if map_show_completed else [])

            fig_map = go.Figure()
            for cat in categories:
                sub = map_df[map_df["_Category"] == cat]
                if sub.empty:
                    continue
                fig_map.add_trace(go.Scattermapbox(
                    lat=sub["Site Latitude"],
                    lon=sub["Site Longitude"],
                    mode="markers",
                    name=cat,
                    marker=dict(
                        size=9,
                        color=MAP_COLORS.get(cat, "#aaa"),
                        opacity=0.85,
                    ),
                    customdata=sub[["Fuze Site ID", "Market", "Sub Market", "_ForecastDate", "_VCG", "_VBG"]].values,
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>"
                        "Market: %{customdata[1]}<br>"
                        "Sub Market: %{customdata[2]}<br>"
                        f"Phase: {cat}<br>"
                        "Forecast Date: %{customdata[3]}<br>"
                        "VCG-OFS: %{customdata[4]:,}<br>"
                        "VBG-OFS: %{customdata[5]:,}<extra></extra>"
                    ),
                ))

            fig_map.update_layout(
                mapbox=dict(
                    style="open-street-map",
                    center=dict(lat=map_df["Site Latitude"].mean(), lon=map_df["Site Longitude"].mean()),
                    zoom=4,
                ),
                height=640,
                margin=dict(t=20, b=10, l=0, r=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
            )
            st.plotly_chart(fig_map, width="stretch")

            n_future = map_df["_Category"].isin(PHASES).sum()
            n_comp = (map_df["_Category"] == "Completed").sum()
            n_dropped = (map_df["_Category"] == "Dropped").sum()
            st.caption(f"{len(map_df):,} sites plotted — {n_future:,} future builds · {n_comp:,} completed (red) · {n_dropped:,} dropped (black)")
