# Upper Peninsula Regional Economic Report

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

An interactive dashboard tracking employment, wages, firm formation, and industry composition across the 15 counties of Michigan's Upper Peninsula.

## What it is

A single-page Streamlit + Plotly application that ships in two forms: a fully interactive Streamlit app for local exploration, and a static HTML build publishable to GitHub Pages. The front page is an interactive county map of the Upper Peninsula — hover any county for its latest QCEW snapshot — alongside a comparison of the five largest county economies by employment, business, and wage growth. A county selector drives a per-county deep dive (employment and salary trends, workforce composition, industry landscape, and firm openings/closings).

Data comes from the BLS Quarterly Census of Employment and Wages (QCEW), the Federal Reserve Bank of St. Louis (FRED), and the IRS Statistics of Income migration files.

## Attribution

This project is adapted from Bryan Cutsinger's **South Florida Economic Report** (https://github.com/bryanpcutsinger/south-florida-economic-report), used under the MIT License. The data pipeline, component architecture, and static-build machinery are his; this fork re-geographies the report to the Upper Peninsula, adds the interactive county map and largest-county comparison, and applies Northern Michigan University branding.

## Quick start (developers)

```bash
git clone <this-repo-url>
cd "Regional Report"
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export FRED_API_KEY=your_key_here   # optional; without it, FRED-based KPIs render as "—"
streamlit run app.py
```

First load fetches the QCEW data for all 15 UP counties and caches to `data/cache/`. Subsequent runs load from disk. The interactive county map fetches the US-counties GeoJSON once and caches it to `data/cache/us_counties.geojson`.

## Configuration (FRED API key)

The Real GDP and unemployment-rate KPI cells come from FRED and need a free API key (get one instantly at https://fredaccount.stlouisfed.org/apikeys). Everything else — the county map, growth charts, trends, treemap, and firm-formation — comes from BLS QCEW and needs no key; without a FRED key those two KPI cells simply render as "—".

Copy `.env.example` to `.env` and add your own key:

```bash
cp .env.example .env
# then edit .env:  FRED_API_KEY=your_key_here
```

`.env` is gitignored and loaded automatically (via `python-dotenv`) by both `streamlit run app.py` and `python build.py`. **Use your own key** — FRED keys are tied to an individual account and rate limit; never commit one or reuse someone else's. For the GitHub Action, store the key as a repository secret instead:

```bash
gh secret set FRED_API_KEY --repo <owner>/<repo>
```

## Building the static site

```bash
python build.py
```

This writes `docs/index.html` plus standalone iframe-embeddable pages under `docs/embeds/`: the interactive county map (`up-map.html`), the largest-county comparison (`up-top-counties.html`), and per-county KPI snapshots and chart pages for the five largest county economies. The GitHub Actions workflow at `.github/workflows/update-data.yml` runs this command on a weekly schedule and commits the refreshed HTML back to the repo.

## Geography

The report covers the 15 counties of Michigan's Upper Peninsula (state FIPS 26): Alger, Baraga, Chippewa, Delta, Dickinson, Gogebic, Houghton, Iron, Keweenaw, Luce, Mackinac, Marquette, Menominee, Ontonagon, and Schoolcraft. BLS suppresses QCEW industry detail for confidentiality in the smallest counties; suppressed cells render as "N/A" on the map and "—" on the KPI cards rather than as zeros.

## Branding

Northern Michigan University palette: NMU Green `#095339` (Pantone 343 C) and NMU Gold `#FFC425` (Pantone 123 C), with brand-compatible neutrals. Colors are defined once in `data/constants.py`.

## Project layout

```
app.py            Streamlit application (interactive dashboard)
build.py          Static HTML generator (produces docs/index.html + docs/embeds/*)
data/             QCEW, FRED, and IRS SOI fetch + clean + analysis modules
components/       Plotly chart builders (county_map, top_counties, + per-county sections)
utils/            Number formatting + narrative text helpers
docs/             Published GitHub Pages output
.github/workflows Weekly auto-refresh workflow
```

## Data sources

- **U.S. Bureau of Labor Statistics**, Quarterly Census of Employment and Wages (QCEW). https://www.bls.gov/cew/
- **Federal Reserve Bank of St. Louis**, FRED economic data — county real GDP (`REALGDPALL{fips}`) and unemployment rate (`LAUCN{fips}0000000003`) series. https://fred.stlouisfed.org/
- **Internal Revenue Service**, Statistics of Income (SOI) county-to-county migration data. https://www.irs.gov/statistics/soi-tax-stats-migration-data

## License

MIT — see [`LICENSE`](LICENSE). Original work © Bryan Cutsinger; see Attribution above.
