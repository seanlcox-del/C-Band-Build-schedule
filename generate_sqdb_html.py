#!/usr/bin/env python3
"""
SQDB 30-60-90 Dashboard Generator
Usage:  python generate_sqdb_html.py
Output: sqdb_dashboard.html  (same folder as this script)
"""
import json, re, sys
from datetime import date
from pathlib import Path
import pandas as pd

FOLDER      = Path(__file__).parent
TODAY       = date.today()
ONAIR_FILE  = Path(r"C:\Users\v296938\Desktop\04082026 FWA CBAND Capacity_Full Data_data.csv")
OUTPUT      = FOLDER / "sqdb_dashboard.html"
PLOTLY_FILE = FOLDER / "plotly-2.35.2.min.js"
PHASES      = ["30-Day", "60-Day", "90-Day", "120-Day"]

# Read Plotly.js for inline embedding
if PLOTLY_FILE.exists():
    PLOTLY_JS = PLOTLY_FILE.read_text(encoding="utf-8")
    print(f"Embedding Plotly.js ({PLOTLY_FILE.stat().st_size/1024/1024:.1f} MB inline)")
else:
    PLOTLY_JS = None
    print("plotly-2.35.2.min.js not found — falling back to CDN")

def phase_label(month_ts):
    m       = pd.Timestamp(month_ts)
    current = pd.Timestamp(TODAY.replace(day=1))
    diff    = (m.year - current.year)*12 + (m.month - current.month)
    if diff == 0: return "30-Day"
    if diff == 1: return "60-Day"
    if diff == 2: return "90-Day"
    if diff == 3: return "120-Day"
    return "Beyond"

# ── Load weekly files ───────────────────────────────────────────────────────
print("Loading weekly files…")
pat, records = re.compile(r"FWA_CBAND_Forecast_Sites_(\d{8})"), []
all_files = sorted(
    list(FOLDER.glob("**/FWA_CBAND_Forecast_Sites_*.xlsx")) +
    list(FOLDER.glob("**/FWA_CBAND_Forecast_Sites_*.csv"))
)
for f in all_files:
    m = pat.search(f.stem)
    if not m: continue
    snap_date = pd.to_datetime(m.group(1), format="%Y%m%d").date()
    if snap_date.year not in (2025, 2026): continue
    try:
        if f.suffix.lower() == ".csv":
            df = pd.read_csv(f)
        else:
            df = pd.read_excel(f, engine="openpyxl")
        if "Fuze Site ID" not in df.columns: continue
        df["Snapshot"] = snap_date
        # For 2025 snapshot files, keep only rows with 2026 Forecast Month
        if snap_date.year == 2025:
            df["Forecast Month"] = pd.to_datetime(df["Forecast Month"])
            df = df[df["Forecast Month"].dt.year == 2026]
            if df.empty: continue
        records.append(df)
        print(f"  + {f.name}")
    except Exception as e:
        print(f"  ! {f.name}: {e}")

if not records:
    print("ERROR: No forecast files found."); sys.exit(1)

all_df = pd.concat(records, ignore_index=True)
all_df["Forecast Month"] = pd.to_datetime(all_df["Forecast Month"])
all_df["Phase"]          = all_df["Forecast Month"].apply(phase_label)
snapshots   = sorted(all_df["Snapshot"].unique())
latest_snap = max(snapshots)
latest_df   = all_df[all_df["Snapshot"] == latest_snap]
print(f"Latest: {latest_snap}  |  {len(snapshots)} weeks")

# ── On-air dates ─────────────────────────────────────────────────────────────
print("Loading on-air dates…")
onair_map = {}
if ONAIR_FILE.exists():
    odf = pd.read_csv(ONAIR_FILE, usecols=["Fuze Site ID", "On Air Date"])
    odf["On Air Date"] = pd.to_datetime(odf["On Air Date"], errors="coerce")
    raw = (odf.dropna(subset=["Fuze Site ID"])
              .groupby("Fuze Site ID")["On Air Date"]
              .min().dt.strftime("%Y-%m-%d").to_dict())
    onair_map = {str(k): v for k, v in raw.items()}  # normalize keys to str
    print(f"  {len(onair_map):,} sites with On Air Date")
else:
    print(f"  On-air file not found: {ONAIR_FILE}")

# ── Phase KPI ─────────────────────────────────────────────────────────────────
prev_snap = snapshots[-2] if len(snapshots) >= 2 else None
prev_df   = all_df[all_df["Snapshot"] == prev_snap] if prev_snap is not None else pd.DataFrame()

phase_kpi = []
for phase in PHASES:
    sub   = latest_df[latest_df["Phase"] == phase]
    sites = int(sub["Fuze Site ID"].nunique())
    vcg   = int(sub["VCG-OFS"].sum())
    vbg   = int(sub["VBG-OFS"].sum())
    d_sites = d_vcg = d_vbg = None
    if prev_snap is not None:
        ps      = prev_df[prev_df["Phase"] == phase]
        d_sites = sites - int(ps["Fuze Site ID"].nunique())
        d_vcg   = vcg   - int(ps["VCG-OFS"].sum())
        d_vbg   = vbg   - int(ps["VBG-OFS"].sum())
    phase_kpi.append({"phase": phase, "sites": sites, "vcg": vcg, "vbg": vbg,
                      "dSites": d_sites, "dVcg": d_vcg, "dVbg": d_vbg})

# ── WoW trend ─────────────────────────────────────────────────────────────────
trend_rows = []
for snap in snapshots:
    sdf = all_df[all_df["Snapshot"] == snap]
    for phase in PHASES:
        sub = sdf[sdf["Phase"] == phase]
        trend_rows.append({"snap": str(snap), "phase": phase,
                           "sites": int(sub["Fuze Site ID"].nunique()),
                           "vcg":   int(sub["VCG-OFS"].sum()),
                           "vbg":   int(sub["VBG-OFS"].sum())})

# ── Market breakdown ──────────────────────────────────────────────────────────
mkt_rows = []
in_phase = latest_df[latest_df["Phase"].isin(PHASES)]
for mkt in sorted(in_phase["Market"].dropna().unique()):
    sub = in_phase[in_phase["Market"] == mkt]
    d = {p: int(sub[sub["Phase"]==p]["Fuze Site ID"].nunique()) for p in PHASES}
    total = sum(d.values())
    if total == 0: continue
    mkt_rows.append({"market": mkt, "d30": d["30-Day"], "d60": d["60-Day"], "d90": d["90-Day"], "d120": d["120-Day"],
                     "total": total, "vcg": int(sub["VCG-OFS"].sum()), "vbg": int(sub["VBG-OFS"].sum())})
mkt_rows.sort(key=lambda r: r["total"])

# ── Sub Market breakdown ───────────────────────────────────────────────────────
sm_rows = []
for sm in sorted(in_phase["Sub Market"].dropna().unique()):
    sub = in_phase[in_phase["Sub Market"] == sm]
    d = {p: int(sub[sub["Phase"]==p]["Fuze Site ID"].nunique()) for p in PHASES}
    total = sum(d.values())
    if total == 0: continue
    sm_rows.append({"submarket": sm, "d30": d["30-Day"], "d60": d["60-Day"], "d90": d["90-Day"], "d120": d["120-Day"],
                    "total": total, "vcg": int(sub["VCG-OFS"].sum()), "vbg": int(sub["VBG-OFS"].sum())})
sm_rows.sort(key=lambda r: r["total"])

# Sub Market → Markets mapping (for cascading filter)
sm_to_mkt = {}
for sm in in_phase["Sub Market"].dropna().unique():
    sm_to_mkt[sm] = sorted(in_phase[in_phase["Sub Market"] == sm]["Market"].dropna().unique().tolist())

# ── All-snapshot data for dynamic adherence (JS computes on selected pair) ────
all_snap_data = {}
for snap in snapshots:
    sdf = all_df[all_df["Snapshot"] == snap]
    grp = (sdf.groupby("Fuze Site ID")
              .agg(fm=("Forecast Month", "min"),
                   mkt=("Market", "first"),
                   sm=("Sub Market", "first"),
                   vcg=("VCG-OFS", "sum"),
                   vbg=("VBG-OFS", "sum"))
              .reset_index())
    all_snap_data[str(snap)] = [
        {"id": str(int(r["Fuze Site ID"])),
         "fm": pd.Timestamp(r["fm"]).strftime("%Y-%m"),
         "mkt": str(r["mkt"]) if pd.notna(r["mkt"]) else "",
         "sm":  str(r["sm"])  if pd.notna(r["sm"])  else "",
         "vcg": int(r["vcg"]) if pd.notna(r["vcg"]) else 0,
         "vbg": int(r["vbg"]) if pd.notna(r["vbg"]) else 0}
        for _, r in grp.iterrows()
    ]

onair_ids = list(onair_map.keys())  # string site IDs with on-air dates

# ── Map data ──────────────────────────────────────────────────────────────────
def prep_coords(df):
    df = df.copy()
    df["_lat"] = pd.to_numeric(df.get("Site Latitude",  pd.Series(dtype=float, index=df.index)), errors="coerce")
    df["_lon"] = pd.to_numeric(df.get("Site Longitude", pd.Series(dtype=float, index=df.index)), errors="coerce")
    df = df.dropna(subset=["_lat","_lon"])
    return df[df["_lat"].between(-90,90) & df["_lon"].between(-180,180)]

map_sites = []
for _, r in prep_coords(latest_df[latest_df["Phase"].isin(PHASES)].drop_duplicates("Fuze Site ID")).iterrows():
    fd = pd.Timestamp(r["Forecast Date"]).strftime("%Y-%m-%d") if pd.notna(r.get("Forecast Date")) else "—"
    map_sites.append({"id": str(r["Fuze Site ID"]), "mkt": str(r.get("Market","")),
                      "sub": str(r.get("Sub Market","")), "lat": round(float(r["_lat"]),6),
                      "lon": round(float(r["_lon"]),6), "cat": r["Phase"], "fd": fd,
                      "vcg": int(r.get("VCG-OFS",0) or 0), "vbg": int(r.get("VBG-OFS",0) or 0), "oa": "—"})

latest_ids = set(latest_df["Fuze Site ID"].dropna().unique())
hist_dedup = (all_df[~all_df["Fuze Site ID"].isin(latest_ids)]
              .sort_values("Snapshot", ascending=False).drop_duplicates("Fuze Site ID"))
for _, r in prep_coords(hist_dedup).iterrows():
    sid = str(r["Fuze Site ID"])
    fd  = pd.Timestamp(r["Forecast Date"]).strftime("%Y-%m-%d") if pd.notna(r.get("Forecast Date")) else "—"
    map_sites.append({"id": sid, "mkt": str(r.get("Market","")),
                      "sub": str(r.get("Sub Market","")), "lat": round(float(r["_lat"]),6),
                      "lon": round(float(r["_lon"]),6),
                      "cat": "Completed" if sid in onair_map else "Dropped",
                      "fd": fd, "vcg": int(r.get("VCG-OFS",0) or 0),
                      "vbg": int(r.get("VBG-OFS",0) or 0), "oa": onair_map.get(sid,"—")})

# ── Site detail ───────────────────────────────────────────────────────────────
det_cols = ["Phase","Market","Sub Market","Fuze Site ID","Forecast Date","VCG-OFS","VBG-OFS"]
det = latest_df[latest_df["Phase"].isin(PHASES)][det_cols].copy()
det["Forecast Date"]  = pd.to_datetime(det["Forecast Date"], errors="coerce").dt.strftime("%Y-%m-%d")
det["Fuze Site ID"]   = det["Fuze Site ID"].astype(str)
det["VCG-OFS"] = pd.to_numeric(det["VCG-OFS"], errors="coerce").fillna(0).astype(int)
det["VBG-OFS"] = pd.to_numeric(det["VBG-OFS"], errors="coerce").fillna(0).astype(int)

# Compute Status (On Schedule / Slipped) using earliest snapshot as baseline
_earliest_snap_dt = min(snapshots)
_base_fm_snap = (
    all_df[all_df["Snapshot"] == _earliest_snap_dt]
    .groupby("Fuze Site ID").agg(Base_Month_Snap=("Forecast Month","min")).reset_index()
)
_base_fm_snap["Fuze Site ID"] = _base_fm_snap["Fuze Site ID"].astype(str)
_earliest_fm = (
    all_df.groupby("Fuze Site ID").agg(Base_Month_Early=("Forecast Month","min")).reset_index()
)
_earliest_fm["Fuze Site ID"] = _earliest_fm["Fuze Site ID"].astype(str)
_base_lookup = _base_fm_snap.merge(_earliest_fm, on="Fuze Site ID", how="right")
_base_lookup["Base_Month"] = pd.to_datetime(
    _base_lookup["Base_Month_Snap"].combine_first(_base_lookup["Base_Month_Early"])
)
_base_lookup = _base_lookup[["Fuze Site ID","Base_Month"]]
det = det.merge(_base_lookup, on="Fuze Site ID", how="left")
det["_Comp_Month"] = pd.to_datetime(det["Forecast Date"], errors="coerce")
_latest_snap_month = pd.Timestamp(latest_snap).to_period("M").to_timestamp()

def _det_classify(row):
    if pd.isna(row["_Comp_Month"]):
        return "Slipped"
    if row["_Comp_Month"] < _latest_snap_month:
        return "Slipped"
    if pd.notna(row["Base_Month"]) and row["_Comp_Month"] <= row["Base_Month"]:
        return "On Schedule"
    return "Slipped"

det["Status"] = det.apply(_det_classify, axis=1)
det = det.drop(columns=["Base_Month","_Comp_Month"])
det = det.sort_values(["Status","Phase","Market","Forecast Date"])
detail_data = det.fillna("—").to_dict("records")

print(f"Map sites: {len(map_sites):,}  |  Detail rows: {len(detail_data):,}")

# ── Serialize data to JS ──────────────────────────────────────────────────────
JS_VARS = {
    "__PHASE_KPI__":   json.dumps(phase_kpi),
    "__TREND__":       json.dumps(trend_rows),
    "__MARKET__":      json.dumps(mkt_rows),
    "__SUBMARKET__":   json.dumps(sm_rows),
    "__SM_TO_MKT__":   json.dumps(sm_to_mkt),
    "__ALL_SNAPS__":   json.dumps(all_snap_data),
    "__ONAIR_IDS__":   json.dumps(onair_ids),
    "__ONAIR_MAP__":   json.dumps(onair_map),
    "__MAP_SITES__":   json.dumps(map_sites),
    "__DETAIL__":      json.dumps(detail_data),
    "__LATEST_SNAP__": json.dumps(str(latest_snap)),
    "__TODAY__":       json.dumps(str(TODAY)),
}

# ── HTML template (placeholders, no f-string needed) ─────────────────────────
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SQDB 30-60-90-120 Schedule Tracker</title>
__PLOTLY_SCRIPT__
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif; background: #f0f0f0; color: #222; min-height: 100vh; }

  header { background: #111; color: #fff; padding: 20px 32px 16px; display: flex; align-items: flex-end; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
  header .title-block h1 { font-size: 1.45rem; font-weight: 700; letter-spacing: .3px; }
  header .title-block p  { font-size: .82rem; color: #aaa; margin-top: 3px; }
  header .as-of { font-size: .78rem; color: #888; white-space: nowrap; align-self: center; }

  .tab-bar { background: #1a1a1a; display: flex; padding: 0 32px; border-bottom: 2px solid #2a2a2a; flex-wrap: wrap; }
  .tab-btn { background: none; border: none; border-bottom: 3px solid transparent; color: #aaa; cursor: pointer; font-family: inherit; font-size: .88rem; font-weight: 600; padding: 12px 20px 10px; margin-bottom: -2px; letter-spacing: .4px; transition: color .15s, border-color .15s; }
  .tab-btn:hover { color: #ddd; }
  .tab-btn.active { color: #fff; border-bottom-color: #2196F3; }

  .tab-content { display: none; }
  .tab-content.active { display: block; }
  .page { padding: 28px 32px 48px; max-width: 1440px; margin: 0 auto; }

  .section-title { font-size: .72rem; font-weight: 700; letter-spacing: 1.2px; text-transform: uppercase; color: #666; margin-bottom: 12px; margin-top: 28px; }
  .section-title:first-child { margin-top: 0; }

  .kpi-row   { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 14px; }
  .kpi-row-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 14px; }
  .kpi-row-5 { display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; margin-bottom: 14px; }
  .kpi-card { background: #fff; border-radius: 8px; padding: 18px 20px 14px; box-shadow: 0 1px 4px rgba(0,0,0,.08), 0 0 0 1px rgba(0,0,0,.04); position: relative; overflow: hidden; }
  .kpi-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: #2196F3; }
  .kpi-card.c-blue::before   { background: #0d6efd; }
  .kpi-card.c-green::before  { background: #198754; }
  .kpi-card.c-orange::before { background: #fd7e14; }
  .kpi-card.c-purple::before { background: #6f42c1; }
  .kpi-card.c-red::before    { background: #dc3545; }
  .kpi-label { font-size: .72rem; font-weight: 600; letter-spacing: .6px; text-transform: uppercase; color: #777; margin-bottom: 8px; }
  .kpi-value { font-size: 1.7rem; font-weight: 700; color: #111; line-height: 1; }
  .kpi-sub   { font-size: .78rem; color: #666; margin-top: 5px; }

  .chart-card { background: #fff; border-radius: 8px; padding: 20px 20px 12px; box-shadow: 0 1px 4px rgba(0,0,0,.08), 0 0 0 1px rgba(0,0,0,.04); margin-bottom: 16px; }
  .chart-card .chart-title { font-size: .8rem; font-weight: 700; letter-spacing: .5px; text-transform: uppercase; color: #444; margin-bottom: 14px; }
  .chart-row { display: grid; gap: 16px; }
  .chart-row.col2 { grid-template-columns: 1fr 1fr; }

  .table-scroll { overflow-y: auto; max-height: 480px; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.08), 0 0 0 1px rgba(0,0,0,.04); background: #fff; }
  .data-table { width: 100%; border-collapse: collapse; font-size: .8rem; }
  .data-table th { background: #f5f5f5; border-bottom: 2px solid #ddd; color: #444; font-size: .68rem; font-weight: 700; letter-spacing: .5px; padding: 8px 10px; text-align: left; text-transform: uppercase; position: sticky; top: 0; z-index: 1; }
  .data-table th.right, .data-table td.right { text-align: right; }
  .data-table td { border-bottom: 1px solid #eee; color: #333; padding: 7px 10px; }
  .data-table tr:last-child td { border-bottom: none; }
  .data-table tr:hover td { background: #fafafa; }

  .search-bar { padding: 7px 12px; border: 1px solid #ddd; border-radius: 4px; font-family: inherit; font-size: .82rem; width: 300px; margin-bottom: 10px; }
  .search-bar:focus { outline: none; border-color: #2196F3; }

  .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: .7rem; font-weight: 700; }
  .badge-30  { background: #dbeafe; color: #1d4ed8; }
  .badge-60  { background: #dcfce7; color: #166534; }
  .badge-90  { background: #ffedd5; color: #c2410c; }
  .badge-120 { background: #ede9fe; color: #5b21b6; }

  .map-legend { display: flex; gap: 16px; margin-bottom: 10px; flex-wrap: wrap; }
  .legend-item { display: flex; align-items: center; gap: 6px; font-size: .8rem; color: #555; }
  .legend-dot  { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
  .caption-txt { font-size: .78rem; color: #888; margin-top: 8px; }

  .filter-row { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }
  .filter-group { display: flex; flex-direction: column; gap: 4px; }
  .filter-group label { font-size: .68rem; font-weight: 700; letter-spacing: .5px; text-transform: uppercase; color: #777; }
  .filter-select { padding: 6px 10px; border: 1px solid #ddd; border-radius: 4px; font-family: inherit; font-size: .82rem; min-width: 200px; background: #fff; cursor: pointer; }
  .filter-select:focus { outline: none; border-color: #2196F3; }
  .view-toggle { display: flex; gap: 0; }
  .view-btn { background: #fff; border: 1px solid #ccc; color: #555; cursor: pointer; font-family: inherit; font-size: .82rem; font-weight: 600; padding: 7px 18px; transition: background .15s, color .15s; }
  .view-btn:first-child { border-radius: 4px 0 0 4px; border-right: none; }
  .view-btn:last-child  { border-radius: 0 4px 4px 0; }
  .view-btn.active { background: #1F4E79; color: #fff; border-color: #1F4E79; }

  @media (max-width: 1100px) {
    .kpi-row, .kpi-row-4 { grid-template-columns: repeat(2, 1fr); }
    .chart-row.col2 { grid-template-columns: 1fr; }
  }
  @media (max-width: 640px) {
    .page { padding: 16px; }
    .kpi-row, .kpi-row-4 { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>

<header>
  <div class="title-block">
    <h1>SQDB 30-60-90-120 Schedule Tracker</h1>
    <p>FWA C-Band Forecast &middot; OFS Sites</p>
  </div>
  <span class="as-of" id="header-snap"></span>
</header>

<div class="tab-bar">
  <button class="tab-btn active" onclick="switchTab('overview',  this)">Overview</button>
  <button class="tab-btn"        onclick="switchTab('market',    this)">Market Breakdown</button>
  <button class="tab-btn"        onclick="switchTab('adherence', this)">Schedule Adherence</button>
  <button class="tab-btn"        onclick="switchTab('map',       this)">Site Map</button>
  <button class="tab-btn"        onclick="switchTab('detail',    this)">Site Detail</button>
</div>

<!-- OVERVIEW -->
<div id="tab-overview" class="tab-content active"><div class="page">
  <div class="section-title">Current Forecast</div>
  <div class="kpi-row-4" id="phase-kpi-row"></div>
  <div class="section-title">Week-over-Week Trend</div>
  <div class="chart-card">
    <div class="chart-title">Sites by Phase</div>
    <div id="chart-trend-sites" style="height:320px;"></div>
  </div>
  <div class="chart-row col2">
    <div class="chart-card">
      <div class="chart-title">VCG-OFS by Phase</div>
      <div id="chart-trend-vcg" style="height:260px;"></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">VBG-OFS by Phase</div>
      <div id="chart-trend-vbg" style="height:260px;"></div>
    </div>
  </div>
</div></div>

<!-- MARKET -->
<div id="tab-market" class="tab-content"><div class="page">
  <div class="section-title">Sites by Market &amp; Phase</div>
  <div class="filter-row">
    <div>
      <div style="font-size:.68rem;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:#777;margin-bottom:4px;">View By</div>
      <div class="view-toggle">
        <button class="view-btn active" id="btn-view-sm"  onclick="setMktView('submarket')">Sub Market</button>
        <button class="view-btn"        id="btn-view-mkt" onclick="setMktView('market')">Market</button>
      </div>
    </div>
    <div class="filter-group">
      <label>Sub Market</label>
      <select class="filter-select" id="filter-sm" onchange="onSmChange()">
        <option value="">All Sub Markets</option>
      </select>
    </div>
    <div class="filter-group">
      <label>Market</label>
      <select class="filter-select" id="filter-mkt" onchange="renderMarketChart()">
        <option value="">All Markets</option>
      </select>
    </div>
  </div>
  <div class="chart-card">
    <div class="chart-title" id="market-chart-title">Sites by Sub Market (Stacked by Phase)</div>
    <div id="chart-market-bar" style="height:600px;"></div>
  </div>
  <div class="section-title">Summary Table</div>
  <div class="table-scroll">
    <table class="data-table">
      <thead><tr>
        <th id="mkt-table-col1">Sub Market</th>
        <th class="right">30-Day</th><th class="right">60-Day</th><th class="right">90-Day</th><th class="right">120-Day</th>
        <th class="right">Total</th><th class="right">VCG-OFS</th><th class="right">VBG-OFS</th>
      </tr></thead>
      <tbody id="market-tbody"></tbody>
    </table>
  </div>
</div></div>

<!-- ADHERENCE -->
<div id="tab-adherence" class="tab-content"><div class="page">
  <div class="filter-row">
    <div class="filter-group">
      <label>Baseline Snapshot</label>
      <select class="filter-select" id="adh-base-snap" onchange="onAdhSnapChange()"></select>
    </div>
    <div class="filter-group">
      <label>Compare Snapshot</label>
      <select class="filter-select" id="adh-comp-snap" onchange="renderAdherenceCharts()"></select>
    </div>
    <div class="filter-group">
      <label>Sub Market</label>
      <select class="filter-select" id="adh-filter-sm" onchange="onAdhSmChange()">
        <option value="">All Sub Markets</option>
      </select>
    </div>
    <div class="filter-group">
      <label>Market</label>
      <select class="filter-select" id="adh-filter-mkt" onchange="renderAdherenceCharts()">
        <option value="">All Markets</option>
      </select>
    </div>
  </div>
  <div class="section-title" id="adh-caption" style="margin-bottom:12px;"></div>
  <div class="kpi-row-5" id="adh-kpi-row"></div>
  <div class="chart-card" style="margin-top:16px;">
    <div class="chart-title">Status Trend (Baseline → Each Snapshot)</div>
    <div id="chart-adh-trend" style="height:300px;"></div>
  </div>
  <div class="chart-row col2" style="margin-top:16px;">
    <div class="chart-card">
      <div class="chart-title">Schedule Status</div>
      <div id="chart-adh-donut" style="height:320px;"></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">Slippage Distribution (Months)</div>
      <div id="chart-adh-slip" style="height:320px;"></div>
    </div>
  </div>
  <div class="section-title">Adherence by Market</div>
  <div class="chart-card">
    <div class="chart-title">Sites by Status per Market</div>
    <div id="chart-adh-market" style="height:600px;"></div>
  </div>
  <div class="section-title">Site-Level Detail</div>
  <div class="table-scroll">
    <table class="data-table">
      <thead><tr>
        <th>Fuze Site ID</th><th>Market</th><th>Sub Market</th><th>Status</th>
        <th class="right">Base Month</th><th class="right">Current Month</th><th class="right">Months Slipped</th>
      </tr></thead>
      <tbody id="adh-detail-tbody"></tbody>
    </table>
  </div>
  <p class="caption-txt" id="adh-detail-caption"></p>
</div></div>

<!-- MAP -->
<div id="tab-map" class="tab-content"><div class="page">
  <div class="section-title">Site Map</div>
  <div class="map-legend" style="align-items:center;">
    <span style="font-size:.68rem;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:#777;margin-right:4px;">Show:</span>
    <label class="legend-item" style="cursor:pointer;"><input type="checkbox" id="map-chk-30day"     checked onchange="updateMapVisibility()"><div class="legend-dot" style="background:#0d6efd;margin-left:5px;"></div>30-Day</label>
    <label class="legend-item" style="cursor:pointer;"><input type="checkbox" id="map-chk-60day"     checked onchange="updateMapVisibility()"><div class="legend-dot" style="background:#198754;margin-left:5px;"></div>60-Day</label>
    <label class="legend-item" style="cursor:pointer;"><input type="checkbox" id="map-chk-90day"     checked onchange="updateMapVisibility()"><div class="legend-dot" style="background:#fd7e14;margin-left:5px;"></div>90-Day</label>
    <label class="legend-item" style="cursor:pointer;"><input type="checkbox" id="map-chk-120day"    checked onchange="updateMapVisibility()"><div class="legend-dot" style="background:#6f42c1;margin-left:5px;"></div>120-Day</label>
    <label class="legend-item" style="cursor:pointer;"><input type="checkbox" id="map-chk-completed" checked onchange="updateMapVisibility()"><div class="legend-dot" style="background:#dc3545;margin-left:5px;"></div>Completed</label>
    <label class="legend-item" style="cursor:pointer;"><input type="checkbox" id="map-chk-dropped"   checked onchange="updateMapVisibility()"><div class="legend-dot" style="background:#212529;margin-left:5px;"></div>Dropped</label>
  </div>
  <div style="display:flex; gap:8px; margin-bottom:8px;">
    <button onclick="mapZoom(1)"  style="padding:5px 14px; font-size:1.1rem; font-weight:700; border:1px solid #ccc; border-radius:4px; background:#fff; cursor:pointer;">+</button>
    <button onclick="mapZoom(-1)" style="padding:5px 14px; font-size:1.1rem; font-weight:700; border:1px solid #ccc; border-radius:4px; background:#fff; cursor:pointer;">&#x2212;</button>
  </div>
  <div id="chart-map" style="height:640px; border-radius:8px; overflow:hidden; box-shadow:0 1px 4px rgba(0,0,0,.08);"></div>
  <p class="caption-txt" id="map-caption"></p>
</div></div>

<!-- DETAIL -->
<div id="tab-detail" class="tab-content"><div class="page">
  <div class="section-title">Site History</div>
  <div class="filter-row" style="margin-bottom:8px;">
    <div class="filter-group">
      <label>Fuze Site ID</label>
      <input type="text" class="filter-select" id="hist-site-id" placeholder="Enter site ID&hellip;"
             style="min-width:220px;" onkeydown="if(event.key==='Enter')lookupSiteHistory()">
    </div>
    <div style="margin-top:22px;">
      <button onclick="lookupSiteHistory()"
              style="padding:6px 16px;border:1px solid #2196F3;border-radius:4px;background:#2196F3;color:#fff;font-family:inherit;font-size:.82rem;font-weight:600;cursor:pointer;">Look Up</button>
    </div>
  </div>
  <div id="site-hist-panel" style="display:none;">
    <div class="kpi-row-5" id="site-hist-kpi" style="margin-bottom:16px;"></div>
    <div class="chart-card">
      <div class="chart-title">Forecast Month History</div>
      <div id="chart-site-hist" style="height:280px;"></div>
    </div>
    <div class="table-scroll" style="margin-top:12px;">
      <table class="data-table">
        <thead><tr>
          <th>Snapshot</th><th>Forecast Month</th><th>Phase</th><th>Status</th><th class="right">VCG-OFS</th><th class="right">VBG-OFS</th><th class="right">In Report</th>
        </tr></thead>
        <tbody id="site-hist-tbody"></tbody>
      </table>
    </div>
    <p class="caption-txt" id="site-hist-caption"></p>
    <div style="margin-top:8px;">
      <button onclick="exportSiteHistCSV()"
              style="padding:5px 14px;border:1px solid #198754;border-radius:4px;background:#198754;color:#fff;font-family:inherit;font-size:.82rem;font-weight:600;cursor:pointer;">&#11015; Export CSV</button>
    </div>
  </div>
  <hr style="margin:24px 0;border:none;border-top:1px solid #eee;">
  <div class="section-title">Browse All Sites</div>
  <div class="filter-row">
    <div class="filter-group">
      <label>Sub Market</label>
      <select class="filter-select" id="det-filter-sm" onchange="onDetSmChange()">
        <option value="">All Sub Markets</option>
      </select>
    </div>
    <div class="filter-group">
      <label>Market</label>
      <select class="filter-select" id="det-filter-mkt" onchange="filterDetail()">
        <option value="">All Markets</option>
      </select>
    </div>
    <div class="filter-group">
      <label>Phase</label>
      <select class="filter-select" id="det-filter-phase" onchange="filterDetail()" style="min-width:120px;">
        <option value="">All Phases</option>
        <option value="30-Day">30-Day</option>
        <option value="60-Day">60-Day</option>
        <option value="90-Day">90-Day</option>
        <option value="120-Day">120-Day</option>
      </select>
    </div>
    <div class="filter-group">
      <label>Status</label>
      <select class="filter-select" id="det-filter-status" onchange="filterDetail()" style="min-width:140px;">
        <option value="">All Statuses</option>
        <option value="On Schedule">On Schedule</option>
        <option value="Slipped">Slipped</option>
      </select>
    </div>
    <div class="filter-group">
      <label>Fuze Site ID</label>
      <input type="text" class="filter-select" id="det-filter-id" placeholder="Search site ID…" oninput="filterDetail()" style="min-width:180px;">
    </div>
    <div style="margin-top:22px;">
      <button onclick="exportDetailCSV()" style="padding:6px 16px;border:1px solid #2196F3;border-radius:4px;background:#2196F3;color:#fff;font-family:inherit;font-size:.82rem;font-weight:600;cursor:pointer;">Download CSV</button>
    </div>
  </div>
  <div class="table-scroll">
    <table class="data-table">
      <thead><tr>
        <th>Status</th><th>Phase</th><th>Market</th><th>Sub Market</th><th>Fuze Site ID</th>
        <th>Forecast Date</th><th class="right">VCG-OFS</th><th class="right">VBG-OFS</th>
      </tr></thead>
      <tbody id="detail-tbody"></tbody>
    </table>
  </div>
  <p class="caption-txt" id="detail-caption"></p>
</div></div>

<script>
window.onerror = function(msg,src,line,col,err) {
  var d = document.createElement('div');
  d.style.cssText = 'position:fixed;top:0;left:0;right:0;background:#dc3545;color:#fff;padding:12px 20px;font-family:monospace;font-size:13px;z-index:9999;';
  d.textContent = 'JS Error: ' + msg + '  (line ' + line + ')';
  document.body.appendChild(d);
};
/* DATA */
const PHASE_KPI  = __PHASE_KPI__;
const TREND      = __TREND__;
const MARKET     = __MARKET__;
const SUBMARKET  = __SUBMARKET__;
const SM_TO_MKT  = __SM_TO_MKT__;
const ALL_SNAPS  = __ALL_SNAPS__;
const ONAIR_IDS  = new Set(__ONAIR_IDS__);
const ONAIR_MAP  = __ONAIR_MAP__;
const MAP_SITES  = __MAP_SITES__;
const DETAIL     = __DETAIL__;
const LATEST_SNAP = __LATEST_SNAP__;
const TODAY_STR   = __TODAY__;

/* CONSTANTS */
const PHASE_COLORS = {"30-Day":"#0d6efd","60-Day":"#198754","90-Day":"#fd7e14","120-Day":"#6f42c1","Completed":"#dc3545","Dropped":"#212529"};
const PHASES = ["30-Day","60-Day","90-Day","120-Day"];
const CFG    = {responsive:true, displayModeBar:false};
const LB     = {paper_bgcolor:'#fff', plot_bgcolor:'#fff',
                font:{family:"'Segoe UI', sans-serif", size:11, color:'#444'},
                xaxis:{showgrid:false, tickfont:{size:10}},
                yaxis:{showgrid:true,  gridcolor:'#f0f0f0', tickfont:{size:10}},
                margin:{t:10, r:20, b:40, l:60}};

function fmt(v) { return Number(v).toLocaleString(); }

/* INIT */
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('header-snap').textContent =
    'Latest snapshot: ' + LATEST_SNAP + '  |  Today: ' + TODAY_STR;
  renderPhaseKPI();
  renderTrendCharts();
});

/* ── PHASE KPI ── */
function fmtDelta(d) {
  if (d === null || d === undefined) return '';
  const sign = d > 0 ? '+' : '';
  const col  = d > 0 ? '#198754' : d < 0 ? '#dc3545' : '#888';
  return ' <span style="font-size:.72rem;color:'+col+';">('+sign+d.toLocaleString()+' WoW)</span>';
}
function renderPhaseKPI() {
  const cls = {"30-Day":"c-blue","60-Day":"c-green","90-Day":"c-orange","120-Day":"c-purple"};
  const row = document.getElementById('phase-kpi-row');
  PHASE_KPI.forEach(p => {
    row.innerHTML +=
      '<div class="kpi-card ' + cls[p.phase] + '">' +
      '<div class="kpi-label">' + p.phase + '</div>' +
      '<div class="kpi-value">' + fmt(p.sites) + fmtDelta(p.dSites) + '</div>' +
      '<div class="kpi-sub">Sites</div>' +
      '<div class="kpi-sub">VCG-OFS: <b>' + fmt(p.vcg) + '</b>' + fmtDelta(p.dVcg) + '</div>' +
      '<div class="kpi-sub">VBG-OFS: <b>' + fmt(p.vbg) + '</b>' + fmtDelta(p.dVbg) + '</div></div>';
  });
}

/* ── TREND CHARTS ── */
function renderTrendCharts() {
  const snaps = [...new Set(TREND.map(r=>r.snap))].sort();
  function makeTraces(metric) {
    return PHASES.map(phase => ({
      x: snaps,
      y: snaps.map(s => { const r = TREND.find(t=>t.snap===s&&t.phase===phase); return r?r[metric]:null; }),
      name: phase, mode:'lines+markers',
      line:{color:PHASE_COLORS[phase], width:2}, marker:{size:6},
      hovertemplate:'<b>'+phase+'</b><br>%{x}<br>'+metric+': %{y:,}<extra></extra>',
    }));
  }
  const shared = Object.assign({}, LB, {
    legend:{orientation:'h', x:0, y:1.1, font:{size:10}},
    hovermode:'x unified',
  });
  Plotly.newPlot('chart-trend-sites', makeTraces('sites'),
    Object.assign({}, shared, {yaxis:Object.assign({},LB.yaxis,{rangemode:'tozero',title:'Sites'})}), CFG);
  Plotly.newPlot('chart-trend-vcg', makeTraces('vcg'),
    Object.assign({}, shared, {yaxis:Object.assign({},LB.yaxis,{rangemode:'tozero',title:'VCG-OFS'})}), CFG);
  Plotly.newPlot('chart-trend-vbg', makeTraces('vbg'),
    Object.assign({}, shared, {yaxis:Object.assign({},LB.yaxis,{rangemode:'tozero',title:'VBG-OFS'})}), CFG);
}

/* ── MARKET ── */
let _mktInit = false;
let _mktView  = 'submarket';

function renderMarket() {
  if (!_mktInit) {
    _mktInit = true;
    const smSel = document.getElementById('filter-sm');
    Object.keys(SM_TO_MKT).sort().forEach(sm => {
      smSel.innerHTML += '<option value="'+sm+'">'+sm+'</option>';
    });
    _populateMktFilter('');
  }
  renderMarketChart();
}

function _populateMktFilter(smFilter) {
  const mktSel = document.getElementById('filter-mkt');
  mktSel.innerHTML = '<option value="">All Markets</option>';
  const mkts = smFilter ? (SM_TO_MKT[smFilter]||[]) : [...new Set(MARKET.map(r=>r.market))].sort();
  mkts.forEach(m => { mktSel.innerHTML += '<option value="'+m+'">'+m+'</option>'; });
}

function setMktView(view) {
  _mktView = view;
  document.getElementById('btn-view-sm').classList.toggle('active',  view==='submarket');
  document.getElementById('btn-view-mkt').classList.toggle('active', view==='market');
  renderMarketChart();
}

function onSmChange() {
  const sm = document.getElementById('filter-sm').value;
  _populateMktFilter(sm);
  renderMarketChart();
}

function renderMarketChart() {
  const smFilter  = document.getElementById('filter-sm').value;
  const mktFilter = document.getElementById('filter-mkt').value;
  let data, yKey, label;
  if (_mktView === 'submarket') {
    data  = smFilter ? SUBMARKET.filter(r=>r.submarket===smFilter) : SUBMARKET;
    yKey  = 'submarket';
    label = 'Sites by Sub Market (Stacked by Phase)';
    document.getElementById('mkt-table-col1').textContent = 'Sub Market';
  } else {
    data = MARKET;
    if (smFilter)  { const mkts = SM_TO_MKT[smFilter]||[]; data = data.filter(r=>mkts.includes(r.market)); }
    if (mktFilter) { data = data.filter(r=>r.market===mktFilter); }
    yKey  = 'market';
    label = 'Sites by Market (Stacked by Phase)';
    document.getElementById('mkt-table-col1').textContent = 'Market';
  }
  document.getElementById('market-chart-title').textContent = label;
  const sorted = [...data].sort((a,b)=>a.total-b.total);
  const traces = PHASES.map(phase => ({
    y: sorted.map(r=>r[yKey]),
    x: sorted.map(r => phase==='30-Day'?r.d30:phase==='60-Day'?r.d60:phase==='90-Day'?r.d90:r.d120),
    name:phase, type:'bar', orientation:'h', marker:{color:PHASE_COLORS[phase]},
    hovertemplate:phase+': %{x:,}<extra>%{y}</extra>',
  }));
  const h = Math.max(400, sorted.length * 28 + 120);
  Plotly.react('chart-market-bar', traces, {
    barmode:'stack', paper_bgcolor:'#fff', plot_bgcolor:'#fff',
    font:{family:"'Segoe UI', sans-serif", size:11, color:'#444'},
    xaxis:{showgrid:true, gridcolor:'#f0f0f0', title:'Sites', tickfont:{size:10}},
    yaxis:{showgrid:false, tickfont:{size:10}, automargin:true},
    legend:{orientation:'h', y:-0.06, x:0.5, xanchor:'center', font:{size:11}, traceorder:'normal'},
    margin:{t:10, r:20, b:80, l:160}, height:h,
  }, CFG);
  const tbody = document.getElementById('market-tbody');
  tbody.innerHTML = '';
  [...sorted].reverse().forEach(r => {
    tbody.innerHTML += '<tr><td>'+r[yKey]+'</td>' +
      '<td class="right">'+fmt(r.d30)+'</td><td class="right">'+fmt(r.d60)+'</td>' +
      '<td class="right">'+fmt(r.d90)+'</td><td class="right">'+fmt(r.d120)+'</td><td class="right"><b>'+fmt(r.total)+'</b></td>' +
      '<td class="right">'+fmt(r.vcg)+'</td><td class="right">'+fmt(r.vbg)+'</td></tr>';
  });
}

/* ── ADHERENCE ── */
let _adhInit = false;

function _computeAdh(baseSnap, compSnap) {
  const snaps = Object.keys(ALL_SNAPS).sort();

  // Universe: all sites ever seen across all snapshots
  // baseFm = earliest fm ever seen (fallback), overridden by baseline snapshot value if present
  const siteInfo = {}; // id -> {mkt, sm, baseFm}
  snaps.forEach(s => {
    ALL_SNAPS[s].forEach(r => {
      if (!siteInfo[r.id] || r.fm < siteInfo[r.id].baseFm) {
        siteInfo[r.id] = {mkt: r.mkt, sm: r.sm, baseFm: r.fm};
      }
    });
  });
  // Override baseFm with the baseline snapshot value where available
  (ALL_SNAPS[baseSnap] || []).forEach(r => {
    if (siteInfo[r.id]) siteInfo[r.id].baseFm = r.fm;
  });

  // Comp map from compare snapshot
  const compMap = {};
  (ALL_SNAPS[compSnap] || []).forEach(r => { compMap[r.id] = r.fm; });
  const compSnapFm = compSnap.substring(0, 7);

  return Object.entries(siteInfo).map(([id, site]) => {
    let status, months = 0;
    const compFm = compMap[id];
    if (!compFm) {
      status = ONAIR_IDS.has(id) ? 'Completed' : 'Dropped';
    } else {
      const bDate = new Date(site.baseFm + '-01');
      const cDate = new Date(compFm     + '-01');
      const diff  = (cDate.getFullYear() - bDate.getFullYear()) * 12 +
                    (cDate.getMonth()    - bDate.getMonth());
      if (compFm < compSnapFm) {
        status = 'Slipped'; months = Math.max(0, diff);
      } else if (diff <= 0) {
        status = 'On Schedule';
      } else {
        status = 'Slipped'; months = diff;
      }
    }
    return {id, mkt: site.mkt, sm: site.sm, status, months,
            base: site.baseFm, comp: compFm || '\u2014'};
  });
}

function renderAdherence() {
  if (!_adhInit) {
    _adhInit = true;
    const snaps   = Object.keys(ALL_SNAPS).sort();
    const baseSel = document.getElementById('adh-base-snap');
    const compSel = document.getElementById('adh-comp-snap');
    snaps.forEach((s, i) => {
      baseSel.innerHTML += '<option value="'+s+'"'+(i===0?' selected':'')+'>'+s+'</option>';
      compSel.innerHTML += '<option value="'+s+'"'+(i===snaps.length-1?' selected':'')+'>'+s+'</option>';
    });
    // Populate Sub Market filter from all snapshot data
    const allRows = Object.values(ALL_SNAPS).flat();
    const sms = [...new Set(allRows.map(r=>r.sm).filter(Boolean))].sort();
    const smSel = document.getElementById('adh-filter-sm');
    sms.forEach(sm => { smSel.innerHTML += '<option value="'+sm+'">'+sm+'</option>'; });
    _adhPopulateMktFilter('');
  }
  renderAdherenceCharts();
}

function _adhPopulateMktFilter(smFilter) {
  const mktSel = document.getElementById('adh-filter-mkt');
  mktSel.innerHTML = '<option value="">All Markets</option>';
  const mkts = smFilter ? (SM_TO_MKT[smFilter]||[])
    : [...new Set(Object.values(ALL_SNAPS).flat().map(r=>r.mkt).filter(Boolean))].sort();
  mkts.forEach(m => { mktSel.innerHTML += '<option value="'+m+'">'+m+'</option>'; });
}

function onAdhSnapChange() {
  // Prevent compare being earlier than baseline
  const snaps   = Object.keys(ALL_SNAPS).sort();
  const baseSel = document.getElementById('adh-base-snap');
  const compSel = document.getElementById('adh-comp-snap');
  if (snaps.indexOf(compSel.value) < snaps.indexOf(baseSel.value)) {
    compSel.value = baseSel.value;
  }
  renderAdherenceCharts();
}

function onAdhSmChange() {
  const sm = document.getElementById('adh-filter-sm').value;
  _adhPopulateMktFilter(sm);
  renderAdherenceCharts();
}

function renderAdhTrend(baseSnap, smFilter, mktFilter) {
  const snaps = Object.keys(ALL_SNAPS).sort().filter(s => s >= baseSnap);
  const statuses = ['On Schedule','Slipped','Completed','Dropped'];
  const colors   = {'On Schedule':'#198754','Slipped':'#dc3545','Completed':'#fd7e14','Dropped':'#6c757d'};
  const counts   = {'On Schedule':[],'Slipped':[],'Completed':[],'Dropped':[]};
  snaps.forEach(snap => {
    let d = _computeAdh(baseSnap, snap);
    if (smFilter)  d = d.filter(r => r.sm  === smFilter);
    if (mktFilter) d = d.filter(r => r.mkt === mktFilter);
    statuses.forEach(s => counts[s].push(d.filter(r=>r.status===s).length));
  });
  const traces = statuses.map(s => ({
    x: snaps, y: counts[s], name: s, mode: 'lines+markers',
    line: {color: colors[s], width: 2}, marker: {size: 6},
    hovertemplate: '<b>'+s+'</b><br>%{x}<br>Sites: %{y:,}<extra></extra>',
  }));
  Plotly.react('chart-adh-trend', traces, {
    ...LB,
    xaxis: {showgrid: true, gridcolor: '#f0f0f0', tickfont: {size: 10}},
    yaxis: {showgrid: true, gridcolor: '#f0f0f0', rangemode: 'tozero', title: 'Sites', tickfont: {size: 10}},
    legend: {orientation: 'h', yanchor: 'bottom', y: 1.02, xanchor: 'right', x: 1, font: {size: 11}},
    margin: {t: 30, r: 20, b: 50, l: 60},
  }, CFG);
}

function renderAdherenceCharts() {
  const baseSnap  = document.getElementById('adh-base-snap').value;
  const compSnap  = document.getElementById('adh-comp-snap').value;
  const smFilter  = document.getElementById('adh-filter-sm').value;
  const mktFilter = document.getElementById('adh-filter-mkt').value;
  if (!baseSnap || !compSnap) return;
  document.getElementById('adh-caption').textContent =
    'Baseline: ' + baseSnap + '  \u2192  Compare: ' + compSnap;
  renderAdhTrend(baseSnap, smFilter, mktFilter);
  let data = _computeAdh(baseSnap, compSnap);
  if (smFilter)  data = data.filter(r => r.sm  === smFilter);
  if (mktFilter) data = data.filter(r => r.mkt === mktFilter);

  // KPIs
  const total     = data.length;
  const on        = data.filter(r=>r.status==='On Schedule').length;
  const slipped   = data.filter(r=>r.status==='Slipped').length;
  const completed = data.filter(r=>r.status==='Completed').length;
  const dropped   = data.filter(r=>r.status==='Dropped').length;
  const pct = n => total ? (n/total*100).toFixed(1)+'%' : '\u2014';
  document.getElementById('adh-kpi-row').innerHTML =
    '<div class="kpi-card"><div class="kpi-label">Total Sites (Baseline)</div><div class="kpi-value">'+fmt(total)+'</div></div>' +
    '<div class="kpi-card c-green"><div class="kpi-label">On Schedule</div><div class="kpi-value">'+fmt(on)+'</div><div class="kpi-sub">'+pct(on)+'</div></div>' +
    '<div class="kpi-card c-red"><div class="kpi-label">Slipped</div><div class="kpi-value">'+fmt(slipped)+'</div><div class="kpi-sub">'+pct(slipped)+'</div></div>' +
    '<div class="kpi-card c-red"><div class="kpi-label">Completed</div><div class="kpi-value">'+fmt(completed)+'</div><div class="kpi-sub">'+pct(completed)+'</div></div>' +
    '<div class="kpi-card"><div class="kpi-label">Dropped</div><div class="kpi-value">'+fmt(dropped)+'</div><div class="kpi-sub">'+pct(dropped)+'</div></div>';

  // Donut
  Plotly.react('chart-adh-donut', [{
    labels:['On Schedule','Slipped','Completed','Dropped'],
    values:[on, slipped, completed, dropped],
    type:'pie', hole:0.5,
    marker:{colors:['#198754','#dc3545','#dc3545','#6c757d'], line:{color:'#fff',width:2}},
    textinfo:'label+percent',
    hovertemplate:'%{label}: %{value:,}<extra></extra>',
  }], {paper_bgcolor:'#fff', font:{family:"'Segoe UI', sans-serif", size:11},
       margin:{t:20,r:10,b:10,l:10},
       legend:{orientation:'v', x:1.02, y:.5, font:{size:10}}}, CFG);

  // Slippage distribution
  const slipMap = {};
  data.filter(r=>r.status==='Slipped').forEach(r => { slipMap[r.months] = (slipMap[r.months]||0)+1; });
  const slipKeys = Object.keys(slipMap).map(Number).sort((a,b)=>a-b);
  Plotly.react('chart-adh-slip', [{
    x: slipKeys.map(k=>k+' mo'),
    y: slipKeys.map(k=>slipMap[k]),
    type:'bar', marker:{color:'#dc3545'},
    text: slipKeys.map(k=>slipMap[k]), textposition:'outside',
    hovertemplate:'Slipped %{x}: %{y:,} sites<extra></extra>',
  }], {paper_bgcolor:'#fff', plot_bgcolor:'#fff',
       font:{family:"'Segoe UI', sans-serif", size:11, color:'#444'},
       xaxis:{showgrid:false, title:'Months Slipped', tickfont:{size:10}},
       yaxis:{showgrid:true, gridcolor:'#f0f0f0', rangemode:'tozero', title:'Sites', tickfont:{size:10}},
       margin:{t:30,r:20,b:50,l:60}, showlegend:false}, CFG);

  // Adherence site-level table
  buildAdhDetailRows(data);

  // Market adherence bar — group by market
  const mktMap = {};
  data.forEach(r => {
    if (!r.mkt) return;
    if (!mktMap[r.mkt]) mktMap[r.mkt] = {'On Schedule':0,'Slipped':0,'Completed':0,'Dropped':0};
    mktMap[r.mkt][r.status]++;
  });
  const mkts = Object.keys(mktMap).sort((a,b) => {
    const ta = mktMap[a]['On Schedule']+mktMap[a]['Slipped']+mktMap[a]['Completed']+mktMap[a]['Dropped'];
    const tb = mktMap[b]['On Schedule']+mktMap[b]['Slipped']+mktMap[b]['Completed']+mktMap[b]['Dropped'];
    const pa = ta ? mktMap[a]['On Schedule']/ta : 0;
    const pb = tb ? mktMap[b]['On Schedule']/tb : 0;
    return pa - pb;
  });
  const h = Math.max(400, mkts.length * 22 + 120);
  Plotly.react('chart-adh-market', [
    {name:'On Schedule', type:'bar', orientation:'h', marker:{color:'#198754'},
     y:mkts, x:mkts.map(m=>mktMap[m]['On Schedule']),
     hovertemplate:'On Schedule: %{x:,}<extra>%{y}</extra>'},
    {name:'Slipped', type:'bar', orientation:'h', marker:{color:'#dc3545'},
     y:mkts, x:mkts.map(m=>mktMap[m]['Slipped']),
     hovertemplate:'Slipped: %{x:,}<extra>%{y}</extra>'},
    {name:'Completed', type:'bar', orientation:'h', marker:{color:'#dc3545', opacity:0.5},
     y:mkts, x:mkts.map(m=>mktMap[m]['Completed']),
     hovertemplate:'Completed: %{x:,}<extra>%{y}</extra>'},
    {name:'Dropped', type:'bar', orientation:'h', marker:{color:'#6c757d'},
     y:mkts, x:mkts.map(m=>mktMap[m]['Dropped']),
     hovertemplate:'Dropped: %{x:,}<extra>%{y}</extra>'},
  ], {barmode:'stack', paper_bgcolor:'#fff', plot_bgcolor:'#fff',
      font:{family:"'Segoe UI', sans-serif", size:11, color:'#444'},
      xaxis:{showgrid:true, gridcolor:'#f0f0f0', title:'Sites', tickfont:{size:10}},
      yaxis:{showgrid:false, tickfont:{size:10}, automargin:true},
      legend:{orientation:'h', y:-0.06, x:0.5, xanchor:'center', font:{size:11}},
      margin:{t:10,r:20,b:80,l:160}, height:h}, CFG);
}

/* ── MAP ── */
let _map = false, _mapScale = 1, _mapTraceIdx = {};
function mapZoom(delta) {
  _mapScale = Math.max(0.5, Math.min(8, _mapScale * (delta > 0 ? 1.4 : 0.7)));
  Plotly.relayout('chart-map', {'geo.projection.scale': _mapScale});
}
function updateMapVisibility() {
  if (!_map) return;
  const CAT_IDS = {"30-Day":"map-chk-30day","60-Day":"map-chk-60day","90-Day":"map-chk-90day","120-Day":"map-chk-120day",
                   "Completed":"map-chk-completed","Dropped":"map-chk-dropped"};
  Object.entries(CAT_IDS).forEach(([cat, chkId]) => {
    const idx = _mapTraceIdx[cat];
    if (idx === undefined) return;
    const chk = document.getElementById(chkId);
    Plotly.restyle('chart-map', {visible: chk && chk.checked ? true : false}, [idx]);
  });
}
function renderMap() {
  if (_map) return; _map = true;
  const CATS = ["30-Day","60-Day","90-Day","120-Day","Completed","Dropped"];
  const traces = [];
  CATS.forEach(cat => {
    const sub = MAP_SITES.filter(s=>s.cat===cat);
    if (!sub.length) return;
    _mapTraceIdx[cat] = traces.length;
    const isDone = cat==='Completed'||cat==='Dropped';
    traces.push({
      type:'scattergeo',
      lat:sub.map(s=>s.lat), lon:sub.map(s=>s.lon),
      mode:'markers', name:cat,
      marker:{size:isDone?5:7, color:PHASE_COLORS[cat], opacity:isDone?0.7:0.85,
              line:{width:0}},
      customdata:sub.map(s=>[s.id,s.mkt,s.sub,s.fd,s.vcg,s.vbg,s.oa]),
      hovertemplate:
        '<b>%{customdata[0]}</b><br>Market: %{customdata[1]}<br>Sub Market: %{customdata[2]}<br>' +
        'Phase: '+cat+'<br>' +
        (cat==='Completed'?'On Air Date: %{customdata[6]}<br>':'Forecast Date: %{customdata[3]}<br>') +
        'VCG-OFS: %{customdata[4]:,}<br>VBG-OFS: %{customdata[5]:,}<extra></extra>',
    });
  });
  Plotly.newPlot('chart-map', traces, {
    geo:{
      scope:'usa', projection:{type:'albers usa', scale:1},
      showland:true, landcolor:'#f5f5f5',
      showlakes:true, lakecolor:'#cde',
      showstates:true, statelinecolor:'#ccc', statelinewidth:0.5,
      showcoastlines:true, coastlinecolor:'#aaa', coastlinewidth:0.8,
      bgcolor:'#fff',
    },
    height:640, margin:{t:10,b:10,l:0,r:0},
    legend:{orientation:'h', y:1.01, x:0, font:{size:10}},
    paper_bgcolor:'#fff',
  }, CFG);
  const nF = MAP_SITES.filter(s=>PHASES.includes(s.cat)).length;
  const nC = MAP_SITES.filter(s=>s.cat==='Completed').length;
  const nD = MAP_SITES.filter(s=>s.cat==='Dropped').length;
  document.getElementById('map-caption').textContent =
    MAP_SITES.length.toLocaleString()+' sites plotted \u2014 '+
    nF.toLocaleString()+' future builds \u00b7 '+
    nC.toLocaleString()+' completed (red) \u00b7 '+
    nD.toLocaleString()+' dropped (black)';
}

/* ── DETAIL TABLE ── */
let _det = false, _detFiltered = null;
function renderDetail() {
  if (!_det) {
    _det = true;
    const smSel = document.getElementById('det-filter-sm');
    const sms = [...new Set(DETAIL.map(r=>r['Sub Market']).filter(Boolean))].sort();
    sms.forEach(sm => { smSel.innerHTML += '<option value="'+sm+'">'+sm+'</option>'; });
    _detPopulateMktFilter('');
  }
  filterDetail();
}
function _detPopulateMktFilter(smFilter) {
  const mktSel = document.getElementById('det-filter-mkt');
  mktSel.innerHTML = '<option value="">All Markets</option>';
  const mkts = smFilter ? (SM_TO_MKT[smFilter]||[])
    : [...new Set(DETAIL.map(r=>r.Market).filter(Boolean))].sort();
  mkts.forEach(m => { mktSel.innerHTML += '<option value="'+m+'">'+m+'</option>'; });
}
function onDetSmChange() {
  const sm = document.getElementById('det-filter-sm').value;
  _detPopulateMktFilter(sm);
  filterDetail();
}
function filterDetail() {
  const smFilter     = document.getElementById('det-filter-sm').value;
  const mktFilter    = document.getElementById('det-filter-mkt').value;
  const phaseFilter  = document.getElementById('det-filter-phase').value;
  const statusFilter = document.getElementById('det-filter-status').value;
  const idFilter     = document.getElementById('det-filter-id').value.toLowerCase().trim();
  _detFiltered = DETAIL.filter(r => {
    if (smFilter     && r['Sub Market'] !== smFilter)    return false;
    if (mktFilter    && r.Market        !== mktFilter)   return false;
    if (phaseFilter  && r.Phase         !== phaseFilter) return false;
    if (statusFilter && r.Status        !== statusFilter) return false;
    if (idFilter     && !String(r['Fuze Site ID']).toLowerCase().includes(idFilter)) return false;
    return true;
  });
  buildDetailRows(_detFiltered);
}
function exportDetailCSV() {
  const cols = ['Status','Phase','Market','Sub Market','Fuze Site ID','Forecast Date','VCG-OFS','VBG-OFS'];
  const rows = [cols.join(',')];
  (_detFiltered||DETAIL).forEach(r => {
    rows.push(cols.map(c => '"'+String(r[c]||'').replace(/"/g,'""')+'"').join(','));
  });
  const blob = new Blob([rows.join('\\n')], {type:'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'sqdb_site_detail_' + LATEST_SNAP + '.csv';
  a.click();
  URL.revokeObjectURL(a.href);
}
function buildDetailRows(data) {
  const BC = {"30-Day":"badge-30","60-Day":"badge-60","90-Day":"badge-90","120-Day":"badge-120"};
  const SC = {"On Schedule":"#198754","Slipped":"#dc3545"};
  const limit = Math.min(data.length, 3000);
  const parts = [];
  for (let i=0; i<limit; i++) {
    const r = data[i];
    const scol = SC[r.Status] || '#444';
    parts.push(
      '<tr><td style="color:'+scol+';font-weight:600;">'+(r.Status||'')+'</td>' +
      '<td><span class="badge '+(BC[r.Phase]||'')+'">'+(r.Phase||'')+'</span></td>' +
      '<td>'+(r.Market||'')+'</td><td>'+(r['Sub Market']||'')+'</td>' +
      '<td>'+(r['Fuze Site ID']||'')+'</td><td>'+(r['Forecast Date']||'')+'</td>' +
      '<td class="right">'+fmt(r['VCG-OFS'])+'</td>' +
      '<td class="right">'+fmt(r['VBG-OFS'])+'</td></tr>');
  }
  document.getElementById('detail-tbody').innerHTML = parts.join('');
  document.getElementById('detail-caption').textContent =
    (limit < data.length ? 'Showing '+limit.toLocaleString()+' of '+data.length.toLocaleString() : data.length.toLocaleString())+' rows';
}

function buildAdhDetailRows(data) {
  const tbody = document.getElementById('adh-detail-tbody');
  if (!tbody) return;
  const STATUS_COL = {'On Schedule':'#198754','Slipped':'#dc3545','Completed':'#dc3545','Dropped':'#6c757d'};
  const limit = Math.min(data.length, 2000);
  const parts = [];
  for (let i=0; i<limit; i++) {
    const r = data[i];
    const col = STATUS_COL[r.status] || '#444';
    parts.push(
      '<tr style="cursor:pointer;" title="Click to view site history" onclick="goToSiteHistory(' + (r.id||0) + ')">' +
      '<td>'+(r.id||'')+'</td><td>'+(r.mkt||'')+'</td><td>'+(r.sm||'')+'</td>' +
      '<td><span style="color:'+col+';font-weight:600;">'+(r.status||'')+'</span></td>' +
      '<td class="right">'+(r.base||'')+'</td><td class="right">'+(r.comp||'')+'</td>' +
      '<td class="right">'+(r.months>0?r.months:'\u2014')+'</td></tr>');
  }
  tbody.innerHTML = parts.join('');
  const cap = document.getElementById('adh-detail-caption');
  if (cap) cap.textContent = (limit<data.length
    ? 'Showing '+limit.toLocaleString()+' of '+data.length.toLocaleString()
    : data.length.toLocaleString())+' rows';
}

/* ── SITE HISTORY ── */
function phaseLabel(fmStr) {
  const today = new Date(TODAY_STR);
  const cur   = new Date(today.getFullYear(), today.getMonth(), 1);
  const fm    = new Date(fmStr + '-01');
  const diff  = (fm.getFullYear() - cur.getFullYear()) * 12 + (fm.getMonth() - cur.getMonth());
  if (diff === 0) return '30-Day';
  if (diff === 1) return '60-Day';
  if (diff === 2) return '90-Day';
  if (diff === 3) return '120-Day';
  return 'Beyond';
}

function lookupSiteHistory() {
  const siteId = document.getElementById('hist-site-id').value.trim();
  if (!siteId) return;
  const snaps = Object.keys(ALL_SNAPS).sort();

  // Find base FM and first appearance
  let baseFm = null, firstSnap = null, mkt = '', sm = '';
  snaps.forEach(s => {
    const r = ALL_SNAPS[s].find(x => x.id === siteId);
    if (r) {
      if (!firstSnap) { firstSnap = s; mkt = r.mkt; sm = r.sm; }
      if (!baseFm || r.fm < baseFm) baseFm = r.fm;
    }
  });

  if (!baseFm) {
    document.getElementById('site-hist-panel').style.display = 'none';
    alert('No data found for Fuze Site ID: ' + siteId);
    return;
  }

  const onAirDate = ONAIR_MAP[siteId] || '\u2014';

  // KPI row
  document.getElementById('site-hist-kpi').innerHTML =
    '<div class="kpi-card"><div class="kpi-label">Market</div><div class="kpi-value" style="font-size:1rem;">' + (mkt||'\u2014') + '</div></div>' +
    '<div class="kpi-card"><div class="kpi-label">Sub Market</div><div class="kpi-value" style="font-size:1rem;">' + (sm||'\u2014') + '</div></div>' +
    '<div class="kpi-card"><div class="kpi-label">First Snapshot</div><div class="kpi-value" style="font-size:1rem;">' + firstSnap + '</div></div>' +
    '<div class="kpi-card c-blue"><div class="kpi-label">Original FM</div><div class="kpi-value" style="font-size:1rem;">' + baseFm + '</div></div>' +
    '<div class="kpi-card ' + (onAirDate!=='\u2014'?'c-green':'') + '"><div class="kpi-label">On Air Date</div><div class="kpi-value" style="font-size:1rem;">' + onAirDate + '</div></div>';

  // Build history rows
  const rows = [], chartX = [], chartY = [];
  const STATUS_COL = {'On Schedule':'#198754','Slipped':'#dc3545','Completed':'#fd7e14','Dropped':'#6c757d'};
  const BC = {'30-Day':'badge-30','60-Day':'badge-60','90-Day':'badge-90','120-Day':'badge-120'};

  snaps.forEach(s => {
    const r = ALL_SNAPS[s].find(x => x.id === siteId);
    if (r) {
      const snapMonthStr = s.substring(0, 7);
      let status;
      if (r.fm < snapMonthStr) {
        status = 'Slipped';
      } else if (r.fm <= baseFm) {
        status = 'On Schedule';
      } else {
        status = 'Slipped';
      }
      rows.push({snap: s, fm: r.fm, phase: phaseLabel(r.fm), status, vcg: r.vcg||0, vbg: r.vbg||0, inReport: true});
      chartX.push(s);
      chartY.push(r.fm + '-01');
    } else if (firstSnap && s > firstSnap) {
      const status = ONAIR_IDS.has(siteId) ? 'Completed' : 'Dropped';
      rows.push({snap: s, fm: '\u2014', phase: '\u2014', status, vcg: null, vbg: null, inReport: false});
    }
  });

  // Timeline chart
  Plotly.react('chart-site-hist', [
    {type:'scatter', mode:'lines+markers',
     x: chartX, y: chartY,
     name: 'Forecast Month',
     line: {color:'#0d6efd', width:2}, marker: {size:7},
     hovertemplate: 'Snapshot: %{x}<br>Forecast Month: %{y|%b %Y}<extra></extra>'},
    {type:'scatter', mode:'lines',
     x: [chartX[0], chartX[chartX.length-1]],
     y: [baseFm+'-01', baseFm+'-01'],
     line: {color:'#6c757d', width:1, dash:'dash'},
     showlegend: false, hoverinfo: 'skip'},
  ], {
    paper_bgcolor:'#fff', plot_bgcolor:'#fff',
    font: {family:"'Segoe UI', sans-serif", size:11, color:'#444'},
    xaxis: {showgrid:false, tickfont:{size:10}, title:'Snapshot'},
    yaxis: {showgrid:true, gridcolor:'#f0f0f0', tickformat:'%b %Y', title:'Forecast Month', tickfont:{size:10}},
    annotations: [{x:chartX[0], y:baseFm+'-01', text:'Original FM',
      showarrow:false, yshift:12, xanchor:'left', font:{size:11, color:'#6c757d'}}],
    margin: {t:20, r:20, b:50, l:90}, showlegend: false,
  }, CFG);

  // History table
  const parts = [];
  rows.forEach(r => {
    const col   = STATUS_COL[r.status] || '#444';
    const badge = r.phase !== '\u2014'
      ? '<span class="badge '+(BC[r.phase]||'')+'">'+r.phase+'</span>' : '\u2014';
    parts.push(
      '<tr><td>'+r.snap+'</td><td>'+r.fm+'</td><td>'+badge+'</td>' +
      '<td style="color:'+col+';font-weight:600;">'+r.status+'</td>' +
      '<td class="right">'+(r.vcg!==null?fmt(r.vcg):'\u2014')+'</td>' +
      '<td class="right">'+(r.vbg!==null?fmt(r.vbg):'\u2014')+'</td>' +
      '<td class="right">'+(r.inReport?'&#10003;':'&#10007;')+'</td></tr>');
  });
  document.getElementById('site-hist-tbody').innerHTML = parts.join('');

  const activeCount = rows.filter(r => r.inReport).length;
  document.getElementById('site-hist-caption').textContent =
    'Site ' + siteId + ' \u00b7 ' + activeCount + ' snapshots with active data \u00b7 ' + rows.length + ' total rows';
  document.getElementById('site-hist-panel').style.display = 'block';
  window._histExport = {siteId, rows};
}

function exportSiteHistCSV() {
  if (!window._histExport) return;
  const {siteId, rows} = window._histExport;
  const header = ['Snapshot','Forecast Month','Phase','Status','VCG-OFS','VBG-OFS','In Report'];
  const lines = [header.join(',')];
  rows.forEach(r => {
    lines.push([r.snap, r.fm, r.phase, r.status,
      r.vcg !== null ? r.vcg : '',
      r.vbg !== null ? r.vbg : '',
      r.inReport ? 'Yes' : 'No'].join(','));
  });
  const blob = new Blob([lines.join('\\n')], {type:'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'site_' + siteId + '_history.csv';
  a.click();
}

/* ── CLICK-TO-LOOKUP ── */
function goToSiteHistory(siteId) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => {
    if (b.textContent.trim() === 'Site Detail') b.classList.add('active');
  });
  document.getElementById('tab-detail').classList.add('active');
  document.getElementById('hist-site-id').value = siteId;
  setTimeout(function() {
    renderDetail();
    lookupSiteHistory();
    document.getElementById('hist-site-id').scrollIntoView({behavior:'smooth', block:'center'});
  }, 50);
}

/* ── TAB SWITCHING ── */
function switchTab(name, btn) {
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-'+name).classList.add('active');
  if (name==='market')    setTimeout(renderMarket,    50);
  if (name==='adherence') setTimeout(renderAdherence, 50);
  if (name==='map')       setTimeout(renderMap,       50);
  if (name==='detail')    setTimeout(renderDetail,    50);
}
</script>
</body>
</html>"""

# ── Inject data into template ─────────────────────────────────────────────────
html = HTML_TEMPLATE
for placeholder, value in JS_VARS.items():
    html = html.replace(placeholder, value)

# Embed or fall back to CDN for Plotly
if PLOTLY_JS:
    html = html.replace("__PLOTLY_SCRIPT__", "<script>" + PLOTLY_JS + "</script>")
else:
    html = html.replace("__PLOTLY_SCRIPT__", '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>')

OUTPUT.write_text(html, encoding="utf-8")
size_kb = OUTPUT.stat().st_size / 1024
print(f"\nWritten: {OUTPUT}")
print(f"Size: {size_kb:.0f} KB")
print(f"Open: file:///{OUTPUT.as_posix()}")
