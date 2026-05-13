# South Florida Economic Report — Architecture

*Internal architecture reference for the project. New users should start at the [root README](../README.md); this file documents internals for anyone modifying the code.*

Live dashboard: https://bryanpcutsinger.github.io/south-florida-economic-report/

## What this is

A single-page Streamlit + Plotly dashboard analyzing the economies of Palm Beach, Broward, and Miami-Dade counties using BLS Quarterly Census of Employment and Wages (QCEW) data. Features a regional snapshot on the main page with per-county deep-dive tabs. The same components also feed `build.py`, which renders a static HTML version plus standalone iframe-embeddable chart pages for GitHub Pages.

Run with `streamlit run app.py` (interactive) or `python build.py` (static build).

## Project Structure

```
app.py                          # Main Streamlit app — regional snapshot + 3 county tabs
build.py                        # Static HTML generator — produces docs/index.html + docs/embeds/*.html
data/
  constants.py                  # FIPS codes (3 counties), NAICS labels, aggregation levels, FAU color palette
  clean.py                      # QCEW cleaning pipeline + filtering helpers
  analysis.py                   # STL trend decomposition + linear 2Q projection (deseasonalize_trend, project_trend)
  fetch.py                      # QCEW data fetch (BLS CSV API) — county + national caches in data/cache/
  fetch_fred.py                 # FRED API client — county real GDP + unemployment rate (powers KPI secondary row)
  fetch_irs_migration.py        # IRS SOI migration fetcher — net domestic migration per county (KPI secondary row)
  cache/                        # Parquet caches — qcew_data.parquet, qcew_national.parquet, qcew_fred_gdp.parquet, qcew_fred_unrate.parquet, qcew_irs_migration.parquet
components/
  employment_trends.py          # Side-by-side line charts — raw + STL trend + 2-quarter linear projection for employment and salary
  growth_quadrant.py            # Industry Landscape — YoY employment × YoY wage growth; bubbles colored by industry domain (not county); 4 tinted quadrants
  firm_formation.py             # Firm Openings & Closings — quarterly establishment churn aggregated from industry-level QoQ deltas
  employment_treemap.py         # Workforce Composition — treemap of private employment by NAICS sector, colored by FAU industry domain
utils/
  formatting.py                 # fmt_number, fmt_currency, fmt_pct
  narratives.py                 # source_citation(), narrate_employment_trends(), format_industry_list()
docs/                           # Published GitHub Pages output (FAU embeds these URLs — do not rename files)
  embeds/                       # Standalone iframe-embeddable chart HTMLs (one per county × section)
audits/                         # Dated point-in-time data validation reports
.github/workflows/
  update-data.yml               # Weekly Monday refresh — fetches fresh data and rebuilds docs/
```

## Dashboard Layout

### Main Page — Regional Snapshot
- Title and subtitle with data quarter badge
- 3 styled KPI cards (one per county), each showing two rows:
  - Primary (QCEW): Total Employment, Establishments, Average Salary — all with YoY % change.
  - Secondary: Real GDP ($B + YoY %), Unemployment rate (% + YoY pp delta, sign-inverted so falling = green), Net Migration (signed integer, IRS SOI tax-year flow, no arrow). Each cell labels its data period in small gray text.
- Secondary row reads "—" gracefully if `FRED_API_KEY` env var is missing or any fetch fails; primary row is unaffected.

### County Tabs (Palm Beach | Broward | Miami-Dade)
Each tab renders 4 sections for that county:

| # | Section | Component | Chart Type |
|---|---------|-----------|------------|
| 1 | Employment & Salary Trends | `employment_trends.py` | Side-by-side line charts (raw + STL trend + 2Q linear projection) |
| 2 | Workforce Composition | `employment_treemap.py` | Treemap — sectors sized by private employment, colored by FAU industry domain; hover shows employment, establishments, average salary, share. Year buttons below the chart switch the snapshot to the latest quarter of any year back to 2019. |
| 3 | Industry Landscape | `growth_quadrant.py` | Bubble scatter — YoY employment × YoY wage growth |
| 4 | Firm Openings & Closings | `firm_formation.py` | Stacked-relative bar — QoQ establishment additions (blue) vs. losses (red) per quarter, with net line + dashed U.S. benchmark overlay |

## Counties

| County | FIPS | Card Color |
|--------|------|------------|
| Palm Beach | 12099 | FAU Blue (#003366) |
| Broward | 12011 | FAU Red (#CC0000) |
| Miami-Dade | 12086 | FAU Electric Blue (#126BD9) |

## FAU Color Palette

| Name | Hex | Usage |
|------|-----|-------|
| FAU Blue | #003366 | Primary — headers, titles, metric values |
| FAU Red | #CC0000 | Broward accent, negative deltas |
| FAU Dark Gray | #4D4C55 | Body text, labels |
| FAU Gray | #CCCCCC | Borders, tab underlines |
| FAU Electric Blue | #126BD9 | Miami-Dade accent, links |
| FAU Stone | #7A97AB | Available for charts |
| FAU Sky Blue | #D9ECFF | Data badge background |
| FAU Sand | #D4B98B | Available for charts |

White background throughout (no dark theme). Palette sourced from https://www.fau.edu/styleguide/colors/.

## Key Design Decisions

- **Single page, no sidebar** — scroll-through narrative layout with tabs for county drill-downs
- **3 counties**: Palm Beach, Broward, Miami-Dade
- **QCEW data only** for industry sections — all components use BLS QCEW CSV API (no API key needed)
- **2-digit NAICS** (agglvl_code=74) for all industry analysis
- **Ownership codes**: Regional snapshot uses own_code=0 (Total Covered); all industry sections use own_code=5 (Private only)
- **"Unclassified" excluded** from all industry charts
- **Employment measure**: `month3_emplvl` (third month of quarter), aliased as `employment` in clean.py
- **Avg annual wage**: `avg_wkly_wage * 52`, derived in clean.py
- **Location quotients**: `lq_month3_emplvl` and `lq_avg_wkly_wage` — pre-computed by BLS in QCEW CSV
- **Component pattern**: Each component exposes `render(df)` for Streamlit and `build_figure(...)` for the static build — both receive a pre-filtered county DataFrame
- **Streamlit-free build boundary**: `build.py` deliberately runs without importing streamlit (see `requirements-build.txt`). The duplicated KPI HTML helpers (`_delta_html`, `_secondary_row_html`) in `app.py` and `build.py` preserve this separation.
- **Data caching**: All 3 counties cached to `data/cache/qcew_data.parquet`; first load fetches from BLS (~3 min); subsequent loads read from disk

## Data Pipeline

1. `fetch.py` → downloads BLS CSV for each year/quarter/county (3 counties × years × quarters), caches to `qcew_data.parquet`. Also fetches the U.S. national aggregate (area code `US000`, agglvl=10) once and caches to `qcew_national.parquet` for the firm-formation benchmark line.
2. `clean.py` → standardizes types, adds `employment`, `avg_annual_wage`, `is_suppressed`, `industry_label` columns.
3. `app.py` (or `build.py`) → filters `df[df["county_name"] == county]` for each tab, passes to components.
4. Filter helpers in `clean.py`: `get_total_covered(df)`, `get_naics_sectors(df)`, `get_latest_quarter(df)`.
5. `analysis.py` → `deseasonalize_trend(series, period=4, log_transform=False)` returns the STL trend component for use in projections.

For data source citations (BLS QCEW, FRED, IRS SOI), see the [root README](../README.md#data-sources).

## API Keys

- **QCEW**: unauthenticated; no key needed.
- **FRED** (county GDP + unemployment for the secondary KPI row): set `FRED_API_KEY` in the environment. Without it, secondary KPI cells render "—" but the rest of the dashboard works.
- **IRS SOI** (net migration): public download, no key.

## Python Environment

- Python 3.11 (pinned via `.python-version` and `.github/workflows/update-data.yml`)
- venv at `.venv/` for local development
- Key packages: streamlit, plotly, pandas, requests, statsmodels (see `requirements.txt`)
- `requirements-build.txt` is a slimmed-down subset omitting streamlit, used by the CI workflow

## Status

The dashboard is live at the URL above and the iframe embeds are in production use on the FAU website. The weekly GitHub Action keeps everything current.

## Change Log

**2026-05-13** — Repo cleanup for public/professional polish: added root README, LICENSE (MIT), `.python-version`; renamed `CLAUDE.md` to `docs/ARCHITECTURE.md`; removed untracked clutter from repo root.

**2026-05-13** — Added iframe embed outputs for the FAU website (`docs/embeds/`) via `build.py` and weekly auto-refresh workflow.

**Earlier (specialties.py removal)** — Removed the Industry Specialization component (`components/specialties.py`) and trimmed to a trend-only, dynamic-projection-horizon layout (commit b3bfcf3).

**2025-03-18** — Initial dashboard cleanup: removed 27 legacy files from the old multi-tab, multi-county prototype (21 component files, 6 data modules); trimmed dead code from `analysis.py`, `narratives.py`, `formatting.py`, `constants.py`.
