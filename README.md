# SQDB 30-60-90 Tracker

A Streamlit dashboard for tracking FWA C-Band qualified address forecasts across 30, 60, and 90-day build horizons.

## Overview

Loads weekly Excel snapshots (`FWA_CBAND_Forecast_Sites_YYYYMMDD.xlsx`) and provides interactive views for monitoring site forecast progress, schedule adherence, and market-level breakdowns.

## Tabs

| Tab | Description |
|-----|-------------|
| **Week-over-Week Trend** | Site and OFS counts by phase over time, with delta table vs prior week |
| **Cumulative OFS** | Running total of VCG/VBG OFS addresses by forecast date |
| **Snapshot Comparison** | Side-by-side comparison of any two weekly snapshots |
| **Schedule Adherence** | Classifies sites as On Schedule, Slipped, or Completed/Dropped vs a baseline |
| **Market Breakdown** | Sites and OFS by market and phase from the latest snapshot |
| **Site Detail** | Row-level data for the latest snapshot |
| **Site Map** | Interactive map of future build sites (30/60/90-Day) and completed sites |

## Setup

**Requirements**
- Python 3.12+
- Streamlit
- Pandas
- Plotly
- openpyxl

**Install dependencies**
```bash
pip install streamlit pandas plotly openpyxl
```

**Run**
```bash
cd "SQDB OFS SITE FORECAST"
python -m streamlit run sqdb_tracker.py
```

## Data

Place weekly forecast files in the same folder as `sqdb_tracker.py`. Files must follow the naming convention:

```
FWA_CBAND_Forecast_Sites_YYYYMMDD.xlsx
```

Only 2026 files are loaded. Files without a `Fuze Site ID` column (e.g. pivot tables) are skipped automatically.

### Key Columns

| Column | Description |
|--------|-------------|
| `Fuze Site ID` | Unique site identifier |
| `Market` / `Sub Market` | Geographic grouping |
| `Forecast Month` | Month the site is forecasted to complete |
| `Forecast Date` | Specific forecasted completion date |
| `VCG-OFS` / `VBG-OFS` | Qualified address counts |
| `Site Latitude` / `Site Longitude` | Coordinates for map plotting |

## Phase Definitions

Phases are calculated relative to today's date:

| Phase | Meaning |
|-------|---------|
| **30-Day** | Current month |
| **60-Day** | Next month |
| **90-Day** | Two months out |
| **Beyond** | Three or more months out |
