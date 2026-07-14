# Upper Peninsula Economic Report — Architecture

*Internal architecture reference for the project. New users should start at the [root README](../README.md); this file documents internals for anyone modifying the code.*

Live dashboard: https://joshuaingber.github.io/upper-peninsula-economic-report/

*Adapted from Bryan Cutsinger's [South Florida Economic Report](https://github.com/bryanpcutsinger/south-florida-economic-report) (MIT). The data pipeline, component pattern, and static-build machinery are his; this fork re-geographies the report to Michigan's Upper Peninsula and applies Northern Michigan University (NMU) branding.*

> **Accessibility is a hard requirement.** Every published page (`docs/index.html` and every embed
> under `docs/embeds/`) must conform to **WCAG 2.1 Level AA** — the condition under which NMU hosts
> the iframes. Read `docs/accessibility/GUIDELINES.md` before changing anything that affects
> rendered output, regenerate the build, and run `npm run a11y` (0 errors) before committing.

## What this is

A single-page Streamlit + Plotly dashboard covering the **15 counties of Michigan's Upper Peninsula** (state FIPS 26) using BLS Quarterly Census of Employment and Wages (QCEW) data. The main page pairs an interactive county choropleth map with a comparison of the five largest county economies; a county selector then drives a per-county deep dive. The same components feed `build.py`, which renders a static HTML version plus standalone iframe-embeddable chart pages for GitHub Pages.

Run with `streamlit run app.py` (interactive) or `python build.py` (static build).

## Project Structure

```
app.py                          # Main Streamlit app — county map + top-counties + per-county deep dive
build.py                        # Static HTML generator — produces docs/index.html + docs/embeds/*.html
data/
  constants.py                  # 15 UP county FIPS, NAICS labels, ownership codes, NMU color palette + accessible tokens
  clean.py                      # QCEW cleaning pipeline + filtering helpers
  analysis.py                   # STL trend decomposition + linear 2Q projection (deseasonalize_trend, project_trend)
  fetch.py                      # QCEW data fetch (BLS CSV API) — county + national caches in data/cache/
  fetch_fred.py                 # FRED API client — county real GDP + unemployment rate (powers KPI secondary row); rate-limit backoff (honors Retry-After)
  fetch_irs_migration.py        # IRS SOI migration fetcher — net domestic migration per county (KPI secondary row)
  cache/                        # Parquet caches + us_counties.geojson (map geometry)
components/
  county_map.py                 # Interactive UP choropleth — counties shaded by YoY employment growth (NMU diverging scale)
  top_counties.py               # Largest County Economies — grouped bar comparing YoY jobs/establishments/wages for the top N
  employment_trends.py          # Side-by-side line charts — raw + STL trend + 2-quarter linear projection for employment and salary
  growth_quadrant.py            # Industry Landscape — YoY employment × YoY wage growth; bubbles colored by industry domain; 4 tinted quadrants
  firm_formation.py             # Firm Openings & Closings — quarterly establishment churn aggregated from industry-level QoQ deltas
  employment_treemap.py         # Workforce Composition — treemap of private employment by NAICS sector, colored by industry domain
utils/
  formatting.py                 # fmt_number, fmt_currency, fmt_pct
  narratives.py                 # source_citation(), narrate_employment_trends(), format_industry_list()
scripts/
  a11y.mjs                      # Accessibility gate (pa11y-ci) run over docs/ via `npm run a11y`
docs/                           # Published GitHub Pages output (NMU embeds these URLs — do not rename files)
  embeds/                       # Standalone iframe-embeddable chart HTMLs (see docs/embeds/README.md)
  accessibility/GUIDELINES.md   # Binding WCAG 2.1 AA rules — read before changing rendered output
audits/                         # Dated point-in-time data validation reports
.github/workflows/
  update-data.yml               # Weekly Monday refresh — fetches fresh data, rebuilds docs/, runs a11y gate, commits
  accessibility.yml             # CI accessibility check on push — fails the build on WCAG violations
```

## Dashboard Layout

### Main Page — Regional Snapshot
- Title and subtitle with data quarter badge.
- **Upper Peninsula at a Glance** — interactive choropleth of all 15 counties shaded by YoY employment growth (`county_map.py`), with a data table below.
- **Largest County Economies** — grouped bar comparing YoY employment, establishment, and wage growth for the five largest county economies by employment (`top_counties.py`).
- **County selector** — a single-select control (`st.selectbox`, default **Marquette**, the UP's largest economy) that drives a per-county deep dive.
- **KPI card** for the selected county, with two rows:
  - Primary (QCEW): Total Employment, Establishments, Average Salary — all with YoY % change.
  - Secondary: Real GDP ($B + YoY %), Unemployment rate (% + YoY pp delta, sign-inverted so falling = green), Net Migration (signed integer, IRS SOI tax-year flow, no arrow). Each cell labels its data period; suppressed/omitted series render "—".
- Secondary row degrades to "—" if `FRED_API_KEY` is missing or a fetch fails; the primary row is unaffected. FRED fetches retry with exponential backoff on HTTP 429, and the static CI build aborts rather than publishing blanks when a key is set but the fetch fails (last good values are preserved).

### Per-County Deep Dive
The selected county renders 4 sections:

| # | Section | Component | Chart Type |
|---|---------|-----------|------------|
| 1 | Employment & Salary Trends | `employment_trends.py` | Side-by-side line charts (raw + STL trend + 2Q linear projection) |
| 2 | Workforce Composition | `employment_treemap.py` | Treemap — sectors sized by private employment, colored by industry domain; hover shows employment, establishments, average salary, share. Year buttons switch the snapshot back to 2019. |
| 3 | Industry Landscape | `growth_quadrant.py` | Bubble scatter — YoY employment × YoY wage growth |
| 4 | Firm Openings & Closings | `firm_formation.py` | Stacked-relative bar — QoQ establishment additions vs. losses per quarter, with net line + dashed U.S. benchmark overlay |

## Counties

The report covers all **15 UP counties** (state FIPS 26), ordered west→east in `COUNTIES` (`data/constants.py`): Gogebic, Ontonagon, Iron, Houghton, Keweenaw, Baraga, Dickinson, Menominee, Marquette, Alger, Delta, Schoolcraft, Luce, Mackinac, Chippewa.

Per-county KPI cards and detail embeds are generated for the **five largest county economies by employment** (`DETAIL_COUNTY_N = 5` in `build.py`, via `get_top_counties`): typically Marquette, Chippewa, Delta, Houghton, Dickinson. County accent colors come from `COUNTY_COLORS` (a WCAG-safe qualitative palette). BLS suppresses QCEW detail for the smallest counties; suppressed cells render "N/A" (map) or "—" (KPI cards), never zeros.

## NMU Color Palette

Defined once in `data/constants.py`. Brand colors that fail contrast on white are never used for text or thin data marks — an accessibility token layer supplies WCAG-safe substitutes.

| Name | Hex | Usage |
|------|-----|-------|
| NMU Green | #095339 (Pantone 343 C) | Primary — headers, titles, metric values, links |
| NMU Gold | #FFC425 (Pantone 123 C) | Decorative fills only (~1.5:1 on white — never text or thin marks) |
| NMU Red | #C41230 | Negative deltas, map decline end of the diverging scale |
| NMU Light Green | #3F7E5E | Chart series |
| NMU Dark Gray | #3D3D3D | Body text, labels |
| NMU Gray | #CCCCCC | Borders, tab underlines |
| NMU Stone | #7E8C84 | Chart series |
| NMU Pale Green | #E3EFE8 | Data badge background |
| NMU Sand | #D4B98B | Chart series (base) |
| **Accessible tokens** | | |
| NMU Muted | #595959 (~7:1) | Captions, periods, sources, footer |
| NMU Border | #767676 (~4.5:1) | Structural UI borders, focus rings |
| NMU Gold Dark | #8C6608 (~5.2:1) | Gold in data-bearing/text roles |
| NMU Sand Dark | #9C7A3C (~4:1) | Sand in data-bearing roles (bubbles) |

The choropleth uses `MAP_DIVERGING_SCALE` built from the three brand colors (NMU red → gold → green). Typography is **Figtree** (`NMU_FONT_FAMILY`), matching nmu.edu. White background throughout. Palette sourced from https://www.nmu.edu/ brand guidelines.

**Back-compat aliases.** `data/constants.py` still defines `FAU_*` names (e.g. `FAU_BLUE = NMU_GREEN`) that re-point the upstream color variables at the NMU palette, so the whole app re-skins from one place without renaming every import. These are aliases only — no Florida branding reaches rendered output.

## Key Design Decisions

- **Single page, no sidebar** — scroll-through narrative: map → top-counties → county selector → deep dive.
- **15 UP counties**; detail embeds for the 5 largest economies.
- **QCEW data only** for industry sections — BLS QCEW CSV API (no API key needed).
- **2-digit NAICS** (agglvl_code=74) for all industry analysis.
- **Ownership codes**: Regional snapshot uses own_code=0 (Total Covered); industry sections use own_code=5 (Private only).
- **"Unclassified" excluded** from all industry charts.
- **Employment measure**: `month3_emplvl` (third month of quarter), aliased as `employment` in clean.py.
- **Avg annual wage**: `avg_wkly_wage * 52`, derived in clean.py.
- **Component pattern**: each component exposes `render(df)` for Streamlit and `build_figure(...)` for the static build.
- **Streamlit-free build boundary**: `build.py` runs without importing streamlit (see `requirements-build.txt`); duplicated KPI HTML helpers in `app.py`/`build.py` preserve this separation.
- **Accessibility is the build's conformance boundary**: every chart ships an `aria-label`, a text summary, and a full data table; a shared WCAG CSS layer overrides sub-threshold brand colors; the treemap/county controls are native focusable `<button>`s. See `docs/accessibility/GUIDELINES.md`.
- **Data caching**: QCEW cached to `data/cache/qcew_data.parquet`; first load fetches from BLS (~3 min), subsequent loads read from disk. The map geometry caches to `us_counties.geojson`.

## Data Pipeline

1. `fetch.py` → downloads BLS CSV per year/quarter/county for the 15 UP counties, caches to `qcew_data.parquet`. Also fetches the U.S. national aggregate (area `US000`, agglvl=10) once to `qcew_national.parquet` for the firm-formation benchmark line.
2. `clean.py` → standardizes types, adds `employment`, `avg_annual_wage`, `is_suppressed`, `industry_label`.
3. `app.py` (or `build.py`) → filters `df[df["county_name"] == county]`, passes to components.
4. Filter helpers in `clean.py`: `get_total_covered(df)`, `get_naics_sectors(df)`, `get_latest_quarter(df)`; county summaries via `latest_county_summaries(df)`.
5. `analysis.py` → `deseasonalize_trend(series, period=4, log_transform=False)` returns the STL trend for projections.

For data source citations (BLS QCEW, FRED, IRS SOI), see the [root README](../README.md#data-sources).

## API Keys

- **QCEW**: unauthenticated; no key needed.
- **FRED** (county GDP + unemployment for the secondary KPI row): set `FRED_API_KEY`. Without it, secondary KPI cells render "—". Fetches retry with backoff on HTTP 429; the static build aborts (rather than overwriting published values) if a key is set but the fetch fails.
- **IRS SOI** (net migration): public download, no key.

## Python Environment

- Python 3.11 (pinned via `.python-version` and `.github/workflows/update-data.yml`).
- venv at `.venv/` for local development.
- Key packages: streamlit, plotly, pandas, requests, statsmodels (see `requirements.txt`).
- `requirements-build.txt` is a slimmed-down subset omitting streamlit, used by the CI workflow.
- Accessibility gate: Node + `pa11y-ci` (`npm install`, then `npm run a11y`).

## Status

The dashboard is live at the URL above. Per the June 2026 fork, it is being embedded on the NMU Economics Department site via iframe; the weekly GitHub Action keeps everything current, and the accessibility gate guards every refresh. See [`docs/embeds/README.md`](embeds/README.md) for embedding and [`../CONTRIBUTING.md`](../CONTRIBUTING.md) for the maintenance workflow.

## Change Log

*Entries below the NMU fork describe the upstream South Florida Economic Report and are retained for lineage; the current geography/branding is the Upper Peninsula / NMU.*

**2026-07-04/05** — Accessibility hardening for NMU hosting. Made WCAG 2.1 AA a standing build requirement (accessibility CSS token layer, per-chart data tables, native-button controls, focus-visible rings); fixed index heading hierarchy (WCAG 1.3.1); deepened gold/link text contrast; darkened choropleth county borders for non-text contrast; added the `npm run a11y` gate and `accessibility.yml` CI check.

**2026-06-22** — Applied the full NMU palette (green/gold/red + neutrals) and nmu.edu Figtree typography; brand colors that fail contrast on white re-point to accessible tokens.

**2026-06-21** — **Forked from the South Florida Economic Report into the Upper Peninsula (Michigan) regional report**: re-geographied to the 15 UP counties (state FIPS 26), added the interactive county choropleth (`county_map.py`) and largest-county comparison (`top_counties.py`), and repointed the KPI/detail flow to a county selector.

---
*Upstream (South Florida) lineage:*

**2026-06-01** — FRED rate-limit resilience + CI fail-safe: inter-request spacing and exponential backoff on HTTP 429 in `fetch_fred.py`; `build.py` aborts before writing output if a FRED key is set but the fetch returns empty, preserving the last good published values.

**2026-05-15** — Added per-county KPI iframe embeds and treemap workforce-share tiles.

**2026-05-13** — Repo cleanup for public release: added root README, LICENSE (MIT), `.python-version`; renamed `CLAUDE.md` to `docs/ARCHITECTURE.md`; added iframe embed outputs and the weekly auto-refresh workflow.

**Earlier** — Removed the Industry Specialization component; trimmed to a trend-only, dynamic-projection-horizon layout. Initial dashboard cleanup removed legacy multi-tab prototype files and dead code.
