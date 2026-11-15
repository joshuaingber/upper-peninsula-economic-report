# Pipeline

How data moves from the source APIs to the published Upper Peninsula dashboard.

Items marked **TODO** have not been checked against the code yet. Confirm or fix them before committing.

## Overview

The project pulls county-level data for the 15 Upper Peninsula counties from three sources (BLS QCEW, FRED, IRS SOI), cleans it and derives chart-ready tables, builds Plotly charts, and publishes them two ways: a local Streamlit app and a static HTML site on GitHub Pages. A GitHub Action rebuilds the static site weekly.

## Flow

```
FRED API ──► data/fetch_fred.py ──────────► data/cache/qcew_fred_*.parquet ─────────┐
BLS QCEW ──► data/fetch.py ───────────────► data/cache/qcew_data.parquet (counties) ┤
             (counties + U.S. national)     data/cache/qcew_national.parquet (U.S.) ┤
IRS SOI ───► data/fetch_irs_migration.py ─► data/cache/qcew_irs_migration.parquet  ─┤
                                                                                    ▼
                          data/clean.py (clean QCEW, filter, chart-data builders, KPI helpers)
                                                                                    ▼
                                      data/analysis.py (trends, projections)   [TODO]
                                                                                    ▼
                                   components/ (Plotly chart builders, one per section)
                                                      ▼                          ▼
                        app.py (Streamlit, interactive, local)          build.py (static HTML)
                                                                                    ▼
                                                                 docs/index.html + docs/embeds/*
                                                                                    ▼
                                                                 GitHub Pages (published site)

.github/workflows/update-data.yml runs build.py weekly and commits the result.
```

FRED and IRS data take a shortcut through `clean.py`: they are not cleaned, but small helper functions there pull out each county's latest values for the regional snapshot card (see Stage 2).

**TODO:** confirm where `analysis.py` sits relative to `clean.py`. Several calculations (growth quadrant, firm formation) already live in `clean.py`.

## Stage 1: Fetch

All three fetchers save their results as parquet files in `data/cache/`. Note that the QCEW and IRS fetchers return an existing cache as is (no freshness check), while the FRED fetcher always tries a fresh fetch first.

### FRED (`data/fetch_fred.py`)

Series fetched per county:
- Annual real GDP (`REALGDPALL{fips}`), via `fetch_real_gdp()`
- Monthly unemployment rate, not seasonally adjusted (`LAUCN{fips}0000000003`), via `fetch_unemployment_rate()`

How it works:
1. The API key comes from the `FRED_API_KEY` environment variable. A local `.env` file is loaded automatically if `python-dotenv` is installed.
2. With a key, it always tries a fresh fetch first. Counties are fetched one at a time, with a 1-second gap between requests to stay under FRED's burst rate limit.
3. Each series is retried up to 6 times with exponential backoff, starting at 1 second. A 429 response waits for the `Retry-After` header when it is a whole number. Empty responses are retried too.
4. A county whose series is missing or fails is skipped, and the rest are still returned. The result is empty only if every county fails.
5. A successful fetch overwrites the parquet cache. A failed fetch falls back to the last cached copy. With no key, the cache is used directly.
6. If there is no fresh data and no cache, an empty DataFrame is returned and the KPI cells display "—".
7. Both fetch functions are memoized, so `build.py` triggers at most one fetch of each per run.

Cache files (committed to the repo so builds work without an API key):
- `data/cache/qcew_fred_gdp.parquet`
- `data/cache/qcew_fred_unrate.parquet`

### BLS QCEW (`data/fetch.py`)

Two datasets, both from BLS's per-area QCEW CSV endpoint:

**County data** (`fetch_all_data()`):
1. For every county, year, and quarter (`COUNTIES` x `YEARS` x `QUARTERS`), it requests one CSV with a 30-second timeout. Requests run one after another, with no retries or pacing.
2. Files that download successfully are tagged with `county_name` and combined. Any failed request is skipped silently.
3. The result is saved to `data/cache/qcew_data.parquet`. After that, `fetch_all_data()` returns the cache without calling BLS. QCEW updates quarterly with a 6-9 month lag, so there is no reason to fetch on every load.
4. `refresh_data()` forces a re-download and overwrites the cache (county data only). Deleting the cache file has the same effect on the next load.

**U.S. national data** (`fetch_national_data()`):
1. Downloads the `US000` file for each year and quarter and keeps two slices: total covered (`own_code=0`, `agglvl=10`) and private only (`own_code=5`, `agglvl=11`).
2. The private slice is the benchmark for the county firm-formation chart, so it matches the county's private-only industry data.
3. Saved to `data/cache/qcew_national.parquet` as raw BLS columns (not cleaned). If an old cache lacks the private slice, it is re-fetched automatically.

Progress is shown as a Streamlit progress bar when Streamlit is available, otherwise as a console counter.

### IRS SOI migration (`data/fetch_irs_migration.py`)

1. Downloads two national CSV files for the year-pair in `LATEST_IRS_YEAR_PAIR` (`countyinflow{pair}.csv` and `countyoutflow{pair}.csv`), read with latin-1 encoding.
2. For each UP county, it takes the IRS "Total Migration-US and Foreign" summary row from each file (state code 96, county code 0) and reads the `n2` column (number of exemptions, used as a count of people).
3. Net migration is inflow minus outflow. The result has one row per county with `inflow_n2`, `outflow_n2`, `net_exemptions`, `county_name`, and `tax_year` (the later year of the pair, so "2223" gives 2023).
4. Saved to `data/cache/qcew_irs_migration.parquet`. An existing cache is returned as is, so updating `LATEST_IRS_YEAR_PAIR` has no effect until the cache file is deleted.
5. Any download error returns an empty DataFrame silently.

**TODO:** confirm which cache files are committed to the repo. Only the two FRED files appear in `data/cache/` on GitHub, which suggests the QCEW and IRS caches are gitignored. If so, each weekly run downloads them from scratch.

## Stage 2: Clean and derive (`data/clean.py`)

Conventions used throughout:
- **Dates:** quarterly data uses a mid-quarter date (Q1 is February, Q2 May, Q3 August, Q4 November) so points sit on the right calendar grid.
- **Ownership and level codes:** `own_code` 0 is all ownerships and 5 is private. `agglvl_code` 70 is total covered, 71 is total by ownership, and 74 is 2-digit NAICS sector.
- **Suppression:** a row is flagged `is_suppressed` when BLS's `disclosure_code` is "N". Chart builders exclude these rows.

Functions, grouped by purpose:

**Cleaning**
- `clean()` runs on raw county data: strips quotes from code columns, converts numbers, flags suppression, sets `employment` from the third month of the quarter, adds `year_qtr` and `date`, computes `avg_annual_wage` (weekly wage x 52), sorts, and adds `industry_label`.
- `add_date_column()` builds the mid-quarter `date` column. It is also used on national data.

**Filters**
- `get_total_covered()`, `get_naics_sectors()` (private by default), and `get_latest_quarter()`.

**Chart-data builders**
- `latest_county_summaries()`: one row per county with its latest-quarter employment, establishments, annual wage, and YoY changes. Feeds the county map and the top-counties chart.
- `get_growth_quadrant_data()`: latest-quarter private sectors with valid YoY employment and wage growth. Feeds the industry landscape bubble chart.
- `get_employment_treemap_data()`, `get_employment_treemap_years()`, `get_treemap_snapshots()`: sector employment shares for the treemap, one snapshot per year.
- `get_firm_formation_data()`: per quarter, establishments added, establishments lost, and the net change. This is the county-private establishment change with an industry breakdown, not gross firm openings and closings.
- `get_national_qoq_pct()`: U.S. quarter-over-quarter change in establishment count, used as the firm-formation benchmark.

**KPI helpers for the regional snapshot card** (FRED and IRS data)
- `latest_gdp_with_growth()`: latest real GDP in billions and YoY growth as a fraction.
- `latest_unrate_with_yoy()`: latest unemployment rate and the change from the same month a year earlier, matched by month rather than position so gaps in the series don't shift the comparison.
- `latest_irs_net()`: net migration and both years of the migration window.

## Stage 3: Analyze (`data/analysis.py`)

**TODO:** list the main functions. Known from a commit message: trend-only charts and a dynamic projection horizon.

## Stage 4: Chart (`components/`)

**TODO:** list the chart builders. Known from the README: the county map, the largest-county comparison, and per-county sections (employment and salary trends, workforce composition, industry landscape, firm openings and closings).

## Stage 5: Output

- **`app.py`** runs the interactive Streamlit dashboard locally: `streamlit run app.py`.
- **`build.py`** writes the static site: `python build.py`. Output goes to `docs/index.html` and `docs/embeds/`.
- **GitHub Pages** serves `docs/`.

**TODO:** confirm whether `build.py` clears `docs/` before writing.

## Weekly refresh

`.github/workflows/update-data.yml` runs `build.py` on a weekly schedule and commits the regenerated HTML back to the repo. The `FRED_API_KEY` must be set as a repository secret (`gh secret set FRED_API_KEY`). Secrets are not copied when a repo is forked.
