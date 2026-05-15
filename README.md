# South Florida Regional Economic Report

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Live dashboard](https://img.shields.io/badge/dashboard-live-success)](https://bryanpcutsinger.github.io/south-florida-economic-report/)

An interactive dashboard tracking employment, wages, firm formation, and industry composition across Palm Beach, Broward, and Miami-Dade counties.

**Live dashboard:** https://bryanpcutsinger.github.io/south-florida-economic-report/

## What it is

A single-page Streamlit + Plotly application that ships in two forms: a fully interactive Streamlit app for local exploration, and a static HTML build published to GitHub Pages. The static build also produces 16 standalone iframe-embeddable pages — the combined regional snapshot, one snapshot per county, and twelve chart pages — that Florida Atlantic University embeds on the FAU website. Data comes from the BLS Quarterly Census of Employment and Wages (QCEW), the Federal Reserve Bank of St. Louis (FRED), and the IRS Statistics of Income migration files.

## Embedding on the FAU website

The dashboard's charts are published as standalone, self-contained HTML pages designed to be dropped into any page via `<iframe>`. They auto-resize to their content and refresh weekly with no manual action required on the embedding side.

See [`docs/embeds/README.md`](docs/embeds/README.md) for the full embed URL list, the `<iframe>` snippet, and the postMessage auto-resize listener.

## Quick start (developers)

```bash
git clone https://github.com/bryanpcutsinger/south-florida-economic-report.git
cd south-florida-economic-report
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export FRED_API_KEY=your_key_here   # optional; without it, FRED-based KPIs render as "—"
streamlit run app.py
```

First load fetches ~3 minutes of QCEW data and caches to `data/cache/`. Subsequent runs load from disk.

## Building the static embeds

```bash
python build.py
```

This writes `docs/index.html` and the 16 files under `docs/embeds/`. The GitHub Actions workflow at `.github/workflows/update-data.yml` runs this command automatically every Monday at 1:00 AM Eastern and commits the refreshed HTML back to the repo.

## Project layout

```
app.py            Streamlit application (interactive dashboard)
build.py          Static HTML generator (produces docs/index.html + docs/embeds/*)
data/             QCEW, FRED, and IRS SOI fetch + clean + analysis modules
components/       Plotly chart builders (one per dashboard section)
utils/            Number formatting + narrative text helpers
docs/             Published GitHub Pages output (frozen URLs — embedded by FAU)
audits/           Point-in-time data validation reports
.github/workflows Weekly auto-refresh workflow
```

Internal architecture details live in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Data refresh schedule

Every Monday at 1:00 AM Eastern, the GitHub Action regenerates all HTML files from fresh BLS QCEW, FRED, and IRS SOI data and commits the result. GitHub Pages serves the updated versions within ~10 minutes.

## Data sources

- **U.S. Bureau of Labor Statistics**, Quarterly Census of Employment and Wages (QCEW). https://www.bls.gov/cew/
- **Federal Reserve Bank of St. Louis**, FRED economic data — county real GDP and unemployment rate series. https://fred.stlouisfed.org/
- **Internal Revenue Service**, Statistics of Income (SOI) county-to-county migration data. https://www.irs.gov/statistics/soi-tax-stats-migration-data

## Author

Bryan Cutsinger, Florida Atlantic University — bcutsinger@fau.edu

## License

MIT — see [`LICENSE`](LICENSE).
