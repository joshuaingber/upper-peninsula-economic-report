#!/usr/bin/env python3
# Static site builder: turns the cleaned QCEW, FRED, and IRS data into the
# published dashboard pages (main dashboard, landing page, and iframe embeds)
# under docs/.
"""
Build static HTML dashboard from QCEW data for GitHub Pages.

Loads and cleans the QCEW data (data/fetch.py, data/clean.py), builds each
Plotly chart as a JSON figure, and embeds that JSON in self-contained HTML
pages, where Plotly.js draws the charts in the browser. The output is
docs/index.html (full dashboard), docs/custom-page.html (landing page), and
docs/embeds/ (standalone pages for iframes).

Usage:
    python build.py
"""
from __future__ import annotations

import html as _html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from data.fetch import fetch_all_data
from data.aggregate_dataframe import get_aggregate_data
from data.clean import (
    clean, get_total_covered, get_latest_quarter, get_growth_quadrant_data,
    latest_gdp_with_growth, latest_unrate_with_yoy, latest_irs_net,
)
from data.analysis import (
    deseasonalize_trend, project_trend, periods_to_current_quarter,
    merge_mit_ai_safety_sector_rating_with_qcew,
)
from components.growth_quadrant import (
    build_figure as build_growth_quadrant_fig,
    METHODOLOGY_NOTE as _GROWTH_QUADRANT_TEXT,
)

from functools import lru_cache

from components.housing_median_value_tseries import METHODOLOGY_NOTE as _HOUSING_TEXT
HOUSING_NOTE = f'<p class="source"><em>{_HOUSING_TEXT}</em></p>'
# Wraps the growth quadrant's methodology text in a small source-note paragraph.
GROWTH_QUADRANT_NOTE = f'<p class="source"><em>{_GROWTH_QUADRANT_TEXT}</em></p>'
from data.constants import (
    FAU_BLUE, FAU_RED, FAU_DARK_GRAY, FAU_GRAY,
    FAU_ELECTRIC_BLUE, FAU_SKY_BLUE, COUNTY_COLORS, COUNTIES,
    NMU_FONT_FAMILY, GOOGLE_FONTS_IMPORT, PLOTLY_FONT,
    NMU_LINK, NMU_MUTED, NMU_BORDER,
    SECTOR_RATING_CSV_PATH, AI_TARGET_DISPLAY_LABELS, AI_SECTOR_FOOTNOTE,
)
from utils.formatting import fmt_number, fmt_currency, fmt_pct
from utils.narratives import (
    narrate_employment_trends, format_industry_list,
    narrate_median_house_value_trends,
)


def _load_ai_risk_data(qcew_df):
    from data.clean import (
        clean_mit_ai_safety_sector_rating,
        clean_qcew_data_for_AI_risk_embed,
    )

    ratings = clean_mit_ai_safety_sector_rating(
        pd.read_csv(SECTOR_RATING_CSV_PATH)
    )
    workers = clean_qcew_data_for_AI_risk_embed(qcew_df)
    return merge_mit_ai_safety_sector_rating_with_qcew(ratings, workers)

# Sets the output folder (docs/, which GitHub Pages serves) and a minimum
# employment threshold.
DOCS_DIR = Path(__file__).parent / "docs"
MIN_EMPLOYMENT = 100

# Per-county deep dives are generated for every UP county economy (ranked by
# latest employment). All 15 counties × 4 sections = 60 chart embeds plus 15
# KPI embeds; the index renders one county tab at a time, so the per-tab weight
# stays flat. Every county has non-suppressed total-covered data, so each gets a
# valid KPI card and trends; the smallest (e.g. Keweenaw) have sparse industry
# detail, and those charts degrade gracefully to their disclosable sectors.
DETAIL_COUNTY_N = len(COUNTIES)


def _detail_counties(df) -> list[str]:
    """Ask components.top_counties.get_top_counties for the top DETAIL_COUNTY_N counties.

    Returns their county_name values as a list. If that comes back empty, it
    falls back to the first DETAIL_COUNTY_N names in COUNTIES.
    """
    from components.top_counties import get_top_counties
    top = get_top_counties(df, DETAIL_COUNTY_N)
    if not top.empty:
        return top["county_name"].tolist()
    return list(COUNTIES.values())[:DETAIL_COUNTY_N]

def _detail_locations(df):
    """Return Aggregate plus the individual counties."""
    return ["Upper Peninsula", *_detail_counties(df)]
# ── CSS ──────────────────────────────────────────────────────────────────────

# Shared WCAG 2.1 AA layer, appended to BOTH the main and embed stylesheets.
# It (a) overrides the few brand colors that fail contrast on white — bright
# gold links, #888 muted text, #CCCCCC borders — with accessible tokens, and
# (b) adds styles for the new accessible components (visible focus rings,
# screen-reader-only text, collapsible data tables, keyboard year buttons).
# Placed LAST so its rules win on source order over the base definitions.
A11Y_CSS = """
/* ── Accessibility (WCAG 2.1 AA) ─────────────────────────────────────────── */
.kpi-period, .kpi-caption, .source, .footer { color: """ + NMU_MUTED + """; }
.source a, .footer a { color: """ + NMU_LINK + """; text-decoration: underline; }
.tab-bar { border-bottom-color: """ + NMU_BORDER + """; }
.kpi-row.secondary { border-top-color: """ + NMU_BORDER + """; }
.kpi-label { line-height: 1.1; }

/* 2.4.7 Focus Visible — a clearly visible keyboard focus indicator (≥3:1). */
a:focus-visible, button:focus-visible, summary:focus-visible,
[tabindex]:focus-visible {
    outline: 3px solid """ + FAU_BLUE + """;
    outline-offset: 2px;
    border-radius: 2px;
}

/* Screen-reader-only text (visually hidden, still announced). */
.sr-only {
    position: absolute; width: 1px; height: 1px;
    padding: 0; margin: -1px; overflow: hidden;
    clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;
}

/* Each chart is a figure with a visible caption. */
figure.chart-figure { margin: 0; }
figure.chart-figure > figcaption { margin-bottom: 0.75rem; }

/* Collapsible data tables — the machine-readable alternative to each chart. */
.data-table-details { margin: 0.25rem 0 0.75rem; }
.data-table-details > summary {
    cursor: pointer; font-size: 0.9rem; font-weight: 600;
    color: """ + FAU_BLUE + """; padding: 0.35rem 0;
}
.data-table-details > summary:hover { text-decoration: underline; }
.table-scroll { overflow-x: auto; }
table.data-table {
    border-collapse: collapse; width: 100%;
    font-size: 0.85rem; margin-top: 0.5rem;
}
table.data-table caption {
    text-align: left; font-size: 0.85rem;
    color: """ + NMU_MUTED + """; padding-bottom: 0.35rem;
}
table.data-table th, table.data-table td {
    border: 1px solid """ + NMU_BORDER + """;
    padding: 0.3rem 0.55rem; text-align: right;
}
table.data-table thead th { background: """ + FAU_SKY_BLUE + """; color: """ + FAU_BLUE + """; }
table.data-table th[scope="row"] { text-align: left; }

/* Keyboard-operable year selector (treemap) — real buttons, not Plotly SVG. */
.year-select { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.5rem 0 0.25rem; }
.year-select .year-btn {
    font-family: inherit; font-size: 0.85rem; cursor: pointer;
    padding: 0.3rem 0.7rem; border: 1px solid """ + NMU_BORDER + """;
    background: #fff; color: """ + FAU_DARK_GRAY + """; border-radius: 4px;
}
.year-select .year-btn[aria-pressed="true"] {
    background: """ + FAU_BLUE + """; color: #fff; border-color: """ + FAU_BLUE + """;
}
"""

# Stylesheet for the main dashboard page (index.html), with the accessibility
# layer appended last. The landing page also starts from this and adds its own.
CSS = GOOGLE_FONTS_IMPORT + """
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: """ + NMU_FONT_FAMILY + """;
    background-color: #FFFFFF;
    color: """ + FAU_DARK_GRAY + """;
    line-height: 1.6;
    max-width: 1200px;
    margin: 0 auto;
    padding: 1rem 2rem;
}

h1, h2, h3, h4 { color: """ + FAU_BLUE + """; }

/* Header */
.main-title { font-size: 2.2rem; font-weight: 700; margin-bottom: 0; }
.main-subtitle { font-size: 1.0rem; margin-top: 0.25rem; color: """ + FAU_DARK_GRAY + """; }

.data-badge {
    display: inline-block;
    background-color: """ + FAU_SKY_BLUE + """;
    color: """ + FAU_BLUE + """;
    padding: 0.25rem 0.75rem;
    border-radius: 20px;
    font-size: 0.85rem;
    font-weight: 500;
    margin: 1rem 0;
}

/* KPI cards */
.snapshot-row { display: flex; gap: 1rem; margin-bottom: 1.5rem; }
.county-card {
    flex: 1;
    background: linear-gradient(135deg, #F8F9FA 0%, #FFFFFF 100%);
    border-radius: 12px;
    padding: 1.5rem;
    border-left: 5px solid;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.county-card h3 { margin: 0 0 0.8rem 0; font-size: 1.3rem; }
.kpi-row { display: flex; justify-content: space-between; gap: 0.8rem; }
.kpi-item { flex: 1; text-align: center; }
.kpi-label {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 0.2rem;
    color: """ + FAU_DARK_GRAY + """;
    min-height: 1.8rem;
    line-height: 0.9rem;
}
.kpi-value { font-size: 1.4rem; font-weight: 700; color: """ + FAU_BLUE + """; }
.kpi-delta { font-size: 0.8rem; margin-top: 0.1rem; }
.kpi-delta.positive { color: #2E7D32; }
.kpi-delta.negative { color: """ + FAU_RED + """; }
/* Secondary KPI row — typography matches the primary row; only the
   separator (border-top) distinguishes them. */
.kpi-row.secondary {
    margin-top: 0.9rem;
    padding-top: 0.7rem;
    border-top: 1px solid """ + FAU_GRAY + """;
}
.kpi-period { font-size: 0.7rem; color: #888; margin-top: 0.15rem; }
.kpi-caption {
    font-size: 0.78rem;
    color: #888;
    margin: -0.5rem 0 1.5rem 0;
    line-height: 1.3;
}

/* Tabs */
.tab-bar {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 0.3rem 0.4rem;
    border-bottom: 2px solid """ + FAU_GRAY + """;
    margin: 1.5rem 0 0 0;
}
.tab-btn {
    padding: 0.6rem 0.5rem;
    font-weight: 500;
    color: """ + FAU_DARK_GRAY + """;
    background: none;
    border: none;
    cursor: pointer;
    font-size: 1rem;
    text-align: center;
    border-bottom: 3px solid transparent;
    font-family: inherit;
}
.tab-btn:hover { color: """ + FAU_BLUE + """; }
.tab-btn.active { border-bottom-color: """ + FAU_BLUE + """; color: """ + FAU_BLUE + """; }

.tab-content { display: none; padding-top: 1rem; }
.tab-content.active { display: block; }

/* Chart sections */
.section { margin: 2rem 0; }
.section h2 { font-size: 1.5rem; margin-bottom: 0.5rem; }
.section p { margin-bottom: 0.75rem; }

.chart-row { display: flex; gap: 1rem; }
.chart-col { flex: 1; min-width: 0; }

.divider { border-top: 1px solid #EEEEEE; margin: 2rem 0; }

.source {
    font-size: 0.8rem;
    color: #888;
    margin-top: 0.25rem;
}
.source a { color: """ + FAU_ELECTRIC_BLUE + """; text-decoration: none; }
.source a:hover { text-decoration: underline; }

.footer {
    font-size: 0.8rem;
    color: #888;
    text-align: center;
    margin-top: 2rem;
    padding: 1rem 0;
    border-top: 1px solid #EEE;
}
.footer a { color: """ + FAU_ELECTRIC_BLUE + """; }

@media (max-width: 768px) {
    .snapshot-row, .chart-row { flex-direction: column; }
    body { padding: 0.5rem 1rem; }
    /* 3 columns (not 2) keeps the 15 counties in even rows — no orphan. */
    .tab-bar { grid-template-columns: repeat(3, 1fr); gap: 0.2rem; }
    .tab-btn { padding: 0.5rem 0.3rem; font-size: 0.85rem; }
}
""" + A11Y_CSS

# ── JavaScript ───────────────────────────────────────────────────────────────

# Keyboard-accessible treemap year selector: HTML buttons toggle which Plotly
# trace (one per year) is visible, replacing Plotly's non-focusable SVG
# updatemenus. Shared by the main dashboard and the embeds.
TREEMAP_JS = """
function selectTreemapYear(btn) {
    var target = btn.getAttribute('data-target');
    var idx = parseInt(btn.getAttribute('data-trace'), 10);
    var n = parseInt(btn.getAttribute('data-count'), 10);
    var vis = [];
    for (var i = 0; i < n; i++) { vis.push(i === idx); }
    Plotly.restyle(target, {visible: vis});
    btn.parentNode.querySelectorAll('.year-btn').forEach(function(b) {
        b.setAttribute('aria-pressed', b === btn ? 'true' : 'false');
    });
}
"""

# Script for the main dashboard: county tab switching (with a chart resize so
# hidden charts redraw correctly) and drawing every chart in figureData.
JS = TREEMAP_JS + """
function renderChart(divId) {
    var el = document.getElementById(divId);
    if (!el || el.dataset.rendered || !figureData[divId]) return;
    el.dataset.rendered = '1';
    var fig = figureData[divId];
    Plotly.newPlot(divId, fig.data, fig.layout, {responsive: true, displayModeBar: false});
}

function showTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(function(el) { el.classList.remove('active'); });
    document.querySelectorAll('.tab-btn').forEach(function(el) {
        el.classList.remove('active');
        el.setAttribute('aria-pressed', 'false');
    });
    document.getElementById(tabId).classList.add('active');
    var btn = document.querySelector('[data-tab="' + tabId + '"]');
    btn.classList.add('active');
    btn.setAttribute('aria-pressed', 'true');
    // Render this county's charts the first time its tab is revealed (deferred
    // from load so all 15 counties don't plot at once), then resize now that
    // the tab is visible.
    document.querySelectorAll('#' + tabId + ' .plotly-chart').forEach(function(el) {
        renderChart(el.id);
    });
    setTimeout(function() {
        document.querySelectorAll('#' + tabId + ' .plotly-chart').forEach(function(el) {
            if (el.data) Plotly.Plots.resize(el);
        });
    }, 50);
}

// Plot only the charts visible at load — the overview charts plus the active
// county tab. Charts inside inactive county tabs render lazily via showTab the
// first time that county is opened; plotting all 15 counties up front froze the
// page and blocked tab switching.
Object.keys(figureData).forEach(function(divId) {
    var el = document.getElementById(divId);
    if (!el) return;
    var tab = el.closest('.tab-content');
    if (tab && !tab.classList.contains('active')) return;
    renderChart(divId);
});
"""

# ── Embed CSS / JS (used by wrap_as_embed) ───────────────────────────────────
# Trimmed copy of CSS — drops .tab-*, .main-title, .main-subtitle, .data-badge,
# .footer (none of which appear in embed pages). body { max-width:none } so the
# embed fills the iframe width rather than the desktop 1200px cap. Includes a
# media query so the KPI embed stacks its 3 county cards vertically below 768px.

EMBED_CSS = GOOGLE_FONTS_IMPORT + """
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: """ + NMU_FONT_FAMILY + """;
    background-color: #FFFFFF;
    color: """ + FAU_DARK_GRAY + """;
    line-height: 1.6;
    padding: 0.5rem;
}

h1, h2, h3, h4 { color: """ + FAU_BLUE + """; }

/* KPI cards */
.snapshot-row { display: flex; gap: 1rem; margin-bottom: 1rem; }
.snapshot-row.single-county { display: block; max-width: 480px; margin: 0 auto 1rem; }
.county-card {
    flex: 1;
    background: linear-gradient(135deg, #F8F9FA 0%, #FFFFFF 100%);
    border-radius: 12px;
    padding: 1.5rem;
    border-left: 5px solid;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.county-card h3 { margin: 0 0 0.8rem 0; font-size: 1.3rem; }
.kpi-row { display: flex; justify-content: space-between; gap: 0.8rem; }
.kpi-item { flex: 1; text-align: center; }
.kpi-label {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 0.2rem;
    color: """ + FAU_DARK_GRAY + """;
    min-height: 1.8rem;
    line-height: 0.9rem;
}
.kpi-value { font-size: 1.4rem; font-weight: 700; color: """ + FAU_BLUE + """; }
.kpi-delta { font-size: 0.8rem; margin-top: 0.1rem; }
.kpi-delta.positive { color: #2E7D32; }
.kpi-delta.negative { color: """ + FAU_RED + """; }
.kpi-row.secondary {
    margin-top: 0.9rem;
    padding-top: 0.7rem;
    border-top: 1px solid """ + FAU_GRAY + """;
}
.kpi-period { font-size: 0.7rem; color: #888; margin-top: 0.15rem; }
.kpi-caption {
    font-size: 0.78rem;
    color: #888;
    margin: 0.75rem 0 0 0;
    line-height: 1.3;
}

/* Chart sections */
.section { margin: 0; }
.section h2 { font-size: 1.5rem; margin-bottom: 0.5rem; }
.section p { margin-bottom: 0.75rem; }

.chart-row { display: flex; gap: 1rem; }
.chart-col { flex: 1; min-width: 0; }

.source {
    font-size: 0.8rem;
    color: #888;
    margin-top: 0.25rem;
}
.source a { color: """ + FAU_ELECTRIC_BLUE + """; text-decoration: none; }
.source a:hover { text-decoration: underline; }

@media (max-width: 768px) {
    .snapshot-row, .chart-row { flex-direction: column; }
    body { padding: 0.3rem; }
}
""" + A11Y_CSS

# Each embed posts its rendered height to the parent host page via postMessage.
# Debounce (100 ms) + last-height dedupe kill the feedback loop where Plotly's
# responsive: true would re-fire layout when the parent resizes the iframe.
EMBED_JS = TREEMAP_JS + """
Object.keys(figureData).forEach(function(divId) {
    var fig = figureData[divId];
    Plotly.newPlot(divId, fig.data, fig.layout, {responsive: true, displayModeBar: false});
});

(function() {
  var lastHeight = 0, timer;
  function postHeight() {
    clearTimeout(timer);
    timer = setTimeout(function() {
      var h = document.documentElement.scrollHeight;
      if (h === lastHeight) return;
      lastHeight = h;
      window.parent.postMessage({type: 'uper-resize', height: h}, '*');
    }, 100);
  }
  window.addEventListener('load', postHeight);
  window.addEventListener('resize', postHeight);
  setTimeout(postHeight, 800);
  document.querySelectorAll('.plotly-chart').forEach(function(el) {
    el.on && el.on('plotly_afterplot', postHeight);
  });
})();
"""


# Wraps an HTML fragment into a complete, standalone page that can be shown in
# an iframe on another site.
def wrap_as_embed(body_html: str, figures: dict, page_title: str) -> str:
    """Build a full HTML document around body_html using EMBED_CSS and EMBED_JS.

    Each embed is a standalone HTML document: loads Plotly from CDN, bundles
    the trimmed embed CSS, renders the included figures, and posts its content
    height to the parent via postMessage. It also adds a visually hidden h1
    containing page_title (HTML-escaped) so the page has a valid heading
    outline, and serializes `figures` to JSON as the `figureData` variable
    that EMBED_JS reads. CSS isolation is automatic — iframes have their own
    document, so styles cannot collide with the host page.
    """
    figures_json = json.dumps(figures)
    return "\n".join([
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f"<title>{page_title}</title>",
        '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>',
        "<style>",
        EMBED_CSS,
        "</style>",
        "</head>",
        "<body>",
        "<main>",
        # Each embed is its own document, so it needs exactly one h1 for a valid
        # heading outline. It's visually hidden (the design has no visible page
        # title inside the iframe) but announced by screen readers.
        f'<h1 class="sr-only">{_html.escape(page_title)}</h1>',
        body_html,
        "</main>",
        "<script>",
        f"var figureData = {figures_json};",
        EMBED_JS,
        "</script>",
        "</body>",
        "</html>",
    ])


# ── Helpers ──────────────────────────────────────────────────────────────────

# Standard source line shown under every chart section.
SOURCE = '<p class="source">Source: <a href="https://www.bls.gov/cew/">BLS QCEW</a> — Quarterly</p>'
# Methodology note shown under the trends section, explaining the STL trend and
# the projection.
TRENDS_NOTE = (
    '<p class="source"><em>Chart shows the STL trend (raw quarterly values omitted '
    'for clarity). Trend computed via STL decomposition (period=4, robust); salary '
    'on log scale. Projection extrapolates a linear fit through the last 4 trend '
    'points to the current calendar quarter — the horizon shrinks as new QCEW data '
    'is published. BLS does not publish seasonally adjusted QCEW — this is a custom '
    'estimate.</em></p>'
)


# Converts a Plotly figure into a JSON-serializable dict.
def _fig_json(fig):
    """Serialize the figure with fig.to_json() and parse it back with json.loads."""
    return json.loads(fig.to_json())


# ── Accessibility helpers ────────────────────────────────────────────────────
# Each chart is paired with (a) a role="img" mount point carrying a concise
# aria-label and (b) a collapsible, machine-readable data table built from the
# same DataFrame that feeds the chart — the WCAG 1.1.1 text alternative.

# Returns the empty <div> where Plotly will draw a chart, labeled for screen readers.
def _chart_div(div_id, aria_label):
    """Plotly mount point exposed to assistive tech as one labeled image.

    role="img" makes screen readers announce `aria_label` and skip the SVG
    internals Plotly injects at runtime; the adjacent data table carries the
    full numbers. The label is HTML-escaped.
    """
    return (
        f'<div id="{div_id}" class="plotly-chart" role="img" '
        f'aria-label="{_html.escape(aria_label)}"></div>'
    )


# Formats a percentage for a table cell, using a dash when the value is missing.
def _pct_str(v):
    """Return "—" if v is NaN, otherwise v with a sign and one decimal, like "+2.3%"."""
    return "—" if pd.isna(v) else f"{v:+.1f}%"


# Builds a collapsible HTML data table that serves as the text alternative to a chart.
def _data_table_html(caption, columns, rows):
    """Build a WCAG-compliant, collapsible data table.

    columns: header labels; the first names the row-header column.
    rows: iterable of tuples; each row's first cell becomes a <th scope="row">.
    Cell values are pre-formatted strings. All text is HTML-escaped, and the
    table is wrapped in a <details> element with a scrollable container.
    """
    head = "".join(f'<th scope="col">{_html.escape(str(c))}</th>' for c in columns)
    body = []
    for row in rows:
        cells = [f'<th scope="row">{_html.escape(str(row[0]))}</th>']
        cells += [f"<td>{_html.escape(str(v))}</td>" for v in row[1:]]
        body.append("<tr>" + "".join(cells) + "</tr>")
    cap = _html.escape(caption)
    return (
        '<details class="data-table-details">'
        f"<summary>Show data table — {cap}</summary>"
        '<div class="table-scroll">'
        f'<table class="data-table"><caption>{cap}</caption>'
        f"<thead><tr>{head}</tr></thead>"
        f'<tbody>{"".join(body)}</tbody></table>'
        "</div></details>"
    )


def _load_benchmarks(summary):
    """U.S./Michigan totals for the map insets; None (insets omitted) on failure."""
    from components.county_map import load_benchmarks
    try:
        return load_benchmarks(summary)
    except Exception as exc:  # benchmark fetch must never break the build
        print(f"WARNING: map benchmarks unavailable ({exc}); building map without insets")
        return None


def _map_table_html(summary, benchmarks=None):
    """Data table for the county choropleth (one row per county).

    If `benchmarks` (components.county_map.load_benchmarks) is given, Michigan
    and United States rows follow the counties, so the inset maps' hover-only
    values are also in the table (WCAG 1.1.1).
    """
    ordered = summary.sort_values("employment", ascending=False, na_position="last")
    rows = [
        (
            f'{r["county_name"]} County',
            fmt_number(r["employment"]),
            fmt_number(r["qtrly_estabs"]),
            fmt_currency(r["avg_annual_wage"]),
            _pct_str(r.get("oty_emp_pct")),
        )
        for _, r in ordered.iterrows()
    ]
    from components.county_map import BENCHMARK_LABELS
    for name in ("Michigan", "United States"):
        b = (benchmarks or {}).get(name)
        if b is None:
            continue
        rows.append((
            BENCHMARK_LABELS[name],
            fmt_number(b["employment"]),
            fmt_number(b["qtrly_estabs"]),
            fmt_currency(b["avg_annual_wage"]),
            _pct_str(b["oty_emp_pct"]) if b["oty_emp_pct"] is not None else "—",
        ))
    return _data_table_html(
        "Upper Peninsula counties, with Michigan and U.S. totals for comparison — "
        "latest-quarter employment, establishments, average salary, and "
        "year-over-year employment growth",
        ["County", "Employment", "Establishments", "Average Salary",
         "YoY Employment Growth"],
        rows,
    )


# Builds the data table that accompanies the largest-county growth comparison.
def _top_table_html(top):
    """Format one row per county with its YoY employment, establishment, and wage growth."""
    rows = [
        (
            f'{r["county_name"]} County',
            _pct_str(r["oty_emp_pct"]),
            _pct_str(r["oty_estab_pct"]),
            _pct_str(r["oty_wage_pct"]),
        )
        for _, r in top.iterrows()
    ]
    return _data_table_html(
        "Largest Upper Peninsula county economies — year-over-year growth in "
        "employment, establishments, and wages",
        ["County", "YoY Employment", "YoY Establishments", "YoY Wages"],
        rows,
    )


# Returns the small year-over-year change badge (arrow and percent) shown on KPI
# cards, or an empty string if the value is missing.
def _delta_html(pct):
    """Render a YoY percent-change badge.

    Direction is conveyed three ways (WCAG 1.4.1 — never color alone): the
    ▲/▼ glyph, the value, and an aria-label word for screen readers. Zero or
    positive values use the "positive" style and an up arrow; negative values
    use the "negative" style and a down arrow.
    """
    if pd.isna(pct):
        return ""
    css = "positive" if pct >= 0 else "negative"
    arrow = "&#9650;" if pct >= 0 else "&#9660;"
    word = "increased" if pct >= 0 else "decreased"
    label = f"{word} {abs(pct):.1f} percent year over year"
    return f'<div class="kpi-delta {css}" aria-label="{label}">{arrow} {abs(pct):.1f}% YoY</div>'


# ── KPI Card ─────────────────────────────────────────────────────────────────

# Builds the second row of a KPI card: real GDP, unemployment rate, and net
# migration. Any missing value shows "—" and "(unavailable)".
def _secondary_row_html(secondary, county_name=None):
    """Build the second KPI row HTML — Real GDP, Unemployment, Net Migration.

    `secondary` is a dict with optional "gdp", "unrate", and "irs" entries (the
    outputs of the latest_* helpers in data/clean.py). GDP shows billions and a
    YoY badge. Unemployment shows the rate and a percentage-point badge, with
    the color inverted (rising is red, falling is green) because lower is
    better. Migration shows a signed net count with its filing-year window and
    no arrow.
    """
    secondary = secondary or {}
    gdp = secondary.get("gdp") or {}
    unr = secondary.get("unrate") or {}
    irs = secondary.get("irs") or {}
    unr_label = ("Simple Average Unemployment Rate"
                 if county_name == "Upper Peninsula" else "Unemployment rate")
    if gdp:
        gdp_value = f"${gdp['value_billions']:.1f}B"
        growth = gdp["yoy_growth"]
        arrow = "&#9650;" if growth >= 0 else "&#9660;"
        cls = "positive" if growth >= 0 else "negative"
        word = "increased" if growth >= 0 else "decreased"
        glabel = f"{word} {abs(growth)*100:.1f} percent year over year"
        gdp_delta = f'<div class="kpi-delta {cls}" aria-label="{glabel}">{arrow} {abs(growth)*100:.1f}% YoY</div>'
        gdp_period = f'<div class="kpi-period">({gdp["year"]})</div>'
    else:
        gdp_value, gdp_delta, gdp_period = "—", "", '<div class="kpi-period">(unavailable)</div>'

    if unr:
        unr_value = f"{unr['rate']:.1f}%"
        delta = unr["yoy_delta_pp"]
        # Arrow tracks rate direction (▲ rose, ▼ fell). Color INVERTED:
        # rising = red (bad), falling = green (good) — lower-is-better.
        arrow = "&#9650;" if delta >= 0 else "&#9660;"
        cls = "negative" if delta >= 0 else "positive"
        word = "rose" if delta >= 0 else "fell"
        ulabel = f"{word} {abs(delta):.1f} percentage points year over year"
        unr_delta = f'<div class="kpi-delta {cls}" aria-label="{ulabel}">{arrow} {abs(delta):.1f}pp YoY</div>'
        unr_period = f'<div class="kpi-period">({unr["month_label"]})</div>'
    else:
        unr_value, unr_delta, unr_period = "—", "", '<div class="kpi-period">(unavailable)</div>'

    if irs:
        sign = "+" if irs["net_exemptions"] >= 0 else "−"
        irs_value = f"{sign}{abs(irs['net_exemptions']):,}"
        irs_delta = ""  # no arrow on migration — sign is the headline
        irs_period = (
            f'<div class="kpi-period">'
            f'({irs["origin_year"]}→{irs["dest_year"]} filings, US + foreign)'
            f'</div>'
        )
    else:
        irs_value, irs_delta, irs_period = "—", "", '<div class="kpi-period">(unavailable)</div>'

    return (
        f'<div class="kpi-row secondary">'
        f'<div class="kpi-item"><div class="kpi-label">Real GDP</div>'
        f'<div class="kpi-value">{gdp_value}</div>{gdp_delta}{gdp_period}</div>'
        f'<div class="kpi-item"><div class="kpi-label">{unr_label}</div>'
        f'<div class="kpi-value">{unr_value}</div>{unr_delta}{unr_period}</div>'
        f'<div class="kpi-item"><div class="kpi-label">Net Migration</div>'
        f'<div class="kpi-value">{irs_value}</div>{irs_delta}{irs_period}</div>'
        f'</div>'
    )


UP = "Upper Peninsula"


def _secondary_for(county_name, df_gdp, df_unrate, df_irs):
    """Second-row data for a county, or the 15-county aggregate for UP."""
    if county_name != UP:
        return {
            "gdp": latest_gdp_with_growth(df_gdp, county_name),
            "unrate": latest_unrate_with_yoy(df_unrate, county_name),
            "irs": latest_irs_net(df_irs, county_name),
        }

    gdp, unrate, irs = {}, {}, {}

    if not df_gdp.empty:
        n = df_gdp["county_name"].nunique()
        counts = df_gdp.groupby("date")["county_name"].nunique()
        full = counts[counts == n].index
        g = df_gdp[df_gdp["date"].isin(full)]
        g = g.groupby("date", as_index=False)["value"].sum()
        g["county_name"] = UP
        gdp = latest_gdp_with_growth(g, UP)

    if not df_unrate.empty:
        u = df_unrate.groupby("date", as_index=False)["value"].mean()
        u["county_name"] = UP
        unrate = latest_unrate_with_yoy(u, UP)

    if not df_irs.empty:
        year = df_irs["tax_year"].max()
        total = df_irs[df_irs["tax_year"] == year]["net_exemptions"].sum()
        irs = latest_irs_net(
            pd.DataFrame([{"county_name": UP, "tax_year": year, "net_exemptions": total}]),
            UP,
        )

    return {"gdp": gdp, "unrate": unrate, "irs": irs}


def _display_name(county_name):
    return "Upper Peninsula" if county_name == "Upper Peninsula" else f"{county_name} County"

def _latest_housing(county_housing_df):
    """(formatted latest median home value, YoY % or None) — same logic as app.py."""
    if county_housing_df is None or county_housing_df.empty:
        return "—", None
    rows = county_housing_df.sort_values("year")
    latest = rows.iloc[-1]
    val = latest["median_home_value"]
    if pd.isna(val):
        return "—", None
    prior = rows[rows["year"] == latest["year"] - 1]
    pct = None
    if not prior.empty:
        pv = prior.iloc[-1]["median_home_value"]
        if pd.notna(pv) and pv != 0:
            pct = (val - pv) / pv * 100
    return fmt_currency(val), pct

# Builds the HTML for one county's KPI card: employment, establishments, and
# average salary, plus the optional second row.
def build_kpi_card(county_df, county_name, color, secondary=None, housing_df=None):
    """Generate HTML for one county KPI card (primary + optional secondary row).

    Takes the county's latest-quarter total-covered row and shows its
    employment, establishment count, and average annual wage, each with a YoY
    badge from the BLS over-the-year columns. The secondary row comes from
    _secondary_row_html. If the county has no total-covered data, it returns a
    card that says "No data available." The county color is used for the left
    border and the name.
    """
    display = _display_name(county_name)                                              # EDIT 2: new line
    totals = get_total_covered(county_df)
    latest = get_latest_quarter(totals)

    if latest.empty:
        return (
            f'<div class="county-card" style="border-left-color: {color};">'
            f'<h3 style="color: {color};">{display}</h3>'                             # EDIT 2: was {_display_name(county_name)}
            f'<p>No data available.</p></div>'
        )

    row = latest.iloc[0]
    secondary_html = _secondary_row_html(secondary, county_name)                      # EDIT 3: pass county_name

    county_housing = (                                                                # EDIT 4: all new (3 blocks)
        housing_df[housing_df["county_name"] == county_name]
        if housing_df is not None and not housing_df.empty else None
    )
    housing_value, housing_pct = _latest_housing(county_housing)

    return (
        f'<div class="county-card" style="border-left-color: {color};">'
        f'<h3 style="color: {color};">{display}</h3>'                                 # EDIT 2 again
        f'<div class="kpi-row">'
        f'<div class="kpi-item"><div class="kpi-label">Employment</div>'
        f'<div class="kpi-value">{fmt_number(row["employment"])}</div>'
        f'{_delta_html(row.get("oty_month3_emplvl_pct_chg"))}</div>'
        f'<div class="kpi-item"><div class="kpi-label">Establishments</div>'
        f'<div class="kpi-value">{fmt_number(row["qtrly_estabs"])}</div>'
        f'{_delta_html(row.get("oty_qtrly_estabs_pct_chg"))}</div>'
        f'<div class="kpi-item"><div class="kpi-label">Average Salary</div>'
        f'<div class="kpi-value">{fmt_currency(row["avg_annual_wage"])}</div>'
        f'{_delta_html(row.get("oty_avg_wkly_wage_pct_chg"))}</div>'
        f'<div class="kpi-item"><div class="kpi-label">Median Home Value</div>'       # EDIT 4: new 4th item
        f'<div class="kpi-value">{housing_value}</div>'
        f'{_delta_html(housing_pct)}</div>'
        f'</div>{secondary_html}</div>'
    )


# ── Section Builders ─────────────────────────────────────────────────────────
# Each function builds Plotly figures, adds them to `figures` dict,
# and returns the HTML for that dashboard section.

# Builds one trend line chart (the STL trend plus a dotted projection) for a
# county's employment or salary series.
def _trends_chart(totals, y_col, title, color, tickformat, hover_prefix, log_transform):
    """Side-by-side STL-trend chart with linear projection through the current quarter.

    Computes the STL trend of y_col (from quarters that are not suppressed and
    have an establishment count), aligned to all of the county's quarters.
    The projection horizon is periods_to_current_quarter of the last trend
    date, and project_trend extends the trend using a fit on its last 4
    points. The solid "Trend" line and the dotted "Projected" line (with open
    markers) share the county color, and the projected span is shaded and
    labeled "PROJECTED". Hover text shows the year-quarter label, with
    projected points labeled "(projected)". Use log_transform=True for wages.
    """
    indexed = totals.set_index("date").sort_index()
    labels = indexed["year_qtr"]

    stl_input = totals[~totals.get("is_suppressed", False).fillna(False)]
    stl_input = stl_input[stl_input["qtrly_estabs"].notna()]
    trend = deseasonalize_trend(
        stl_input.set_index("date")[y_col].sort_index(),
        log_transform=log_transform,
    ).reindex(indexed.index)

    hovertemplate = (
        "%{customdata}<br>%{fullData.name}: " + hover_prefix + "%{y:,.0f}<extra></extra>"
    )

    trend_observed = trend.dropna()
    periods = (
        periods_to_current_quarter(trend_observed.index[-1])
        if not trend_observed.empty else 0
    )
    projection = project_trend(trend, periods=periods, lookback=4, log_transform=log_transform)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=trend.index, y=trend.values, customdata=labels.values,
        mode="lines", name="Trend",
        line=dict(color=color, width=3), hovertemplate=hovertemplate,
    ))
    if not projection.empty:
        last_trend_x = trend.dropna().index[-1]
        last_trend_y = trend.dropna().iloc[-1]
        proj_x = [last_trend_x] + list(projection.index)
        proj_y = [last_trend_y] + list(projection.values)
        proj_labels = ["Latest trend"] + [
            f"{d.year} Q{ {2:1, 5:2, 8:3, 11:4}[d.month] } (projected)"
            for d in projection.index
        ]
        fig.add_trace(go.Scatter(
            x=proj_x, y=proj_y, customdata=proj_labels,
            mode="lines+markers", name="Projected",
            line=dict(color=color, dash="dot", width=2.5),
            marker=dict(size=7, color=color, symbol="circle-open",
                        line=dict(width=2, color=color)),
            hovertemplate=hovertemplate,
        ))
        fig.add_vrect(
            x0=last_trend_x, x1=projection.index[-1],
            fillcolor=FAU_SKY_BLUE, opacity=0.5,
            layer="below", line_width=0,
            annotation_text="PROJECTED", annotation_position="top right",
            annotation_font=dict(size=9, color=color),
        )

    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        font=dict(family=PLOTLY_FONT),
        plot_bgcolor="white", paper_bgcolor="white",
        hovermode="x unified", height=440,
        margin=dict(t=50, b=90, l=100, r=20),
        legend=dict(orientation="h", yanchor="top", y=-0.22, x=0),
        xaxis=dict(
            showgrid=False,
            title=dict(text="Quarter", standoff=15),
            showline=True, linecolor="black", linewidth=2, mirror=False,
            ticks="outside", tickcolor="black", ticklen=4,
        ),
        yaxis=dict(
            showgrid=False, tickformat=tickformat,
            title=dict(text=title, standoff=15),
            showline=True, linecolor="black", linewidth=2, mirror=False,
            ticks="outside", tickcolor="black", ticklen=4,
        ),
    )
    return fig


# Builds the Employment & Salary Trends section for one county: a narrative,
# two side-by-side trend charts, and a data table. Returns (html, figures).
def build_trends(county_df, county_name, county_id, heading_level=2):
    """Employment & Salary Trends — raw + STL-trend overlays, side by side.

    Returns (html_fragment, figures_dict) so the caller can either merge the
    figures into the main dashboard's master dict (index.html path) or write
    the fragment as a standalone embed page. ``heading_level`` controls the
    section heading tag: 2 for standalone embeds (under their sr-only h1), 4
    for the index detail tabs (under the h3 county name below "County Detail").

    The narrative comes from narrate_employment_trends, extended with the
    change in average annual wage between the first and last quarters. The
    charts come from _trends_chart (employment on a linear scale, salary on a
    log scale). If the county has no total-covered data, it returns a short
    "No trend data available." section and an empty figures dict.
    """
    h, _h = f"h{heading_level}", f"/h{heading_level}"
    totals = get_total_covered(county_df)
    if totals.empty:
        return f'<div class="section"><{h}>Employment &amp; Salary Trends<{_h}><p>No trend data available.</p></div>', {}

    totals = totals.sort_values("date")
    earliest, latest = totals.iloc[0], totals.iloc[-1]
    color = COUNTY_COLORS.get(county_name, FAU_BLUE)

    narrative = narrate_employment_trends(
        county_name=county_name,
        start_year=int(earliest["year"]), end_year=int(latest["year"]),
        start_empl=earliest["employment"], end_empl=latest["employment"],
    )
    sw, ew = earliest["avg_annual_wage"], latest["avg_annual_wage"]
    if pd.notna(sw) and pd.notna(ew) and sw > 0:
        wc = (ew - sw) / sw * 100
        narrative += (
            f" Average annual wages went from {fmt_currency(sw)} to "
            f"{fmt_currency(ew)}, {'rising' if wc >= 0 else 'falling'} "
            f"{abs(wc):.1f}% over the same period."
        )

    fig_e = _trends_chart(totals, "employment", "Total Employment", color, ",.0f", "", log_transform=False)
    fig_w = _trends_chart(totals, "avg_annual_wage", "Average Salary", color, "$,.0f", "$", log_transform=True)

    eid, wid = f"{county_id}-trends-empl", f"{county_id}-trends-wage"
    figures = {eid: _fig_json(fig_e), wid: _fig_json(fig_w)}

    yr0, yr1 = int(earliest["year"]), int(latest["year"])
    empl_aria = f"Trend line of total employment in {_display_name(county_name)}, {yr0} to {yr1}."
    wage_aria = (
        f"Trend line of average annual salary in {_display_name(county_name)}, "
        f"{yr0} to {yr1}, on a logarithmic scale."
    )
    table = _data_table_html(
        f"{_display_name(county_name)} — quarterly total employment and average salary",
        ["Quarter", "Total Employment", "Average Salary"],
        [
            (r["year_qtr"], fmt_number(r["employment"]), fmt_currency(r["avg_annual_wage"]))
            for _, r in totals.iterrows()
        ],
    )

    html = (
        f'<div class="section"><{h}>Employment &amp; Salary Trends<{_h}>'
        f'<figure class="chart-figure"><figcaption>{narrative}</figcaption>'
        f'<div class="chart-row">'
        f'<div class="chart-col">{_chart_div(eid, empl_aria)}</div>'
        f'<div class="chart-col">{_chart_div(wid, wage_aria)}</div>'
        f'</div></figure>{table}{SOURCE}{TRENDS_NOTE}</div>'
    )
    return html, figures


# Builds the Industry Landscape section for one county: a narrative, the growth
# quadrant bubble chart, and a data table. Returns (html, figures).
def build_growth_quadrant(county_df, county_name, county_id, heading_level=2):
    """Growth Quadrant — YoY employment vs salary growth, domain-colored bubbles.

    Gets the chart data from get_growth_quadrant_data. The narrative names up
    to 3 of the largest industries growing on both measures (both rates above
    zero) and up to 2 of the largest shrinking on both (both below zero);
    industries at exactly zero are in neither list. The figure comes from
    components.growth_quadrant, and the data table is sorted by employment. If
    there is no disclosable data, it returns a short message section and an
    empty figures dict.
    """
    h, _h = f"h{heading_level}", f"/h{heading_level}"
    plot_data = get_growth_quadrant_data(county_df)
    if plot_data.empty:
        return f'<div class="section"><{h}>Industry Landscape<{_h}><p>No disclosable industry growth data.</p></div>', {}

    year, qtr = int(plot_data["year"].iloc[0]), int(plot_data["qtr"].iloc[0])

    ne = plot_data[(plot_data["oty_month3_emplvl_pct_chg"] > 0) & (plot_data["oty_avg_wkly_wage_pct_chg"] > 0)]
    sw = plot_data[(plot_data["oty_month3_emplvl_pct_chg"] < 0) & (plot_data["oty_avg_wkly_wage_pct_chg"] < 0)]

    parts = [
        f"Each bubble is a 2-digit NAICS industry in {year} Q{qtr}; size reflects "
        f"total employment. The horizontal split at 0% salary growth and the vertical "
        f"split at 0% employment growth define four regions. Both growth rates are "
        f"year over year."
    ]
    if not ne.empty:
        names = ne.nlargest(3, "employment")["industry_label"].tolist()
        parts.append(f" Industries expanding on both fronts (jobs and pay): {format_industry_list(names)}.")
    if not sw.empty:
        names = sw.nlargest(2, "employment")["industry_label"].tolist()
        parts.append(f" {format_industry_list(names)} are losing both jobs and pay growth.")
    narrative = "".join(parts)

    fig = build_growth_quadrant_fig(plot_data)
    div_id = f"{county_id}-growth-quadrant"
    figures = {div_id: _fig_json(fig)}

    aria = (
        f"Bubble chart of {len(plot_data)} industries in {_display_name(county_name)}, "
        f"{year} Q{qtr}, plotted by year-over-year employment growth (horizontal) "
        f"and wage growth (vertical); bubble size reflects employment."
    )
    table = _data_table_html(
        f"{_display_name(county_name)} — industry employment and year-over-year growth, {year} Q{qtr}",
        ["Industry", "Employment", "YoY Employment Growth", "YoY Wage Growth"],
        [
            (
                r["industry_label"],
                fmt_number(r["employment"]),
                _pct_str(r["oty_month3_emplvl_pct_chg"]),
                _pct_str(r["oty_avg_wkly_wage_pct_chg"]),
            )
            for _, r in plot_data.sort_values("employment", ascending=False).iterrows()
        ],
    )

    html = (
        f'<div class="section"><{h}>Industry Landscape<{_h}>'
        f'<figure class="chart-figure"><figcaption>{narrative}</figcaption>'
        f"{_chart_div(div_id, aria)}</figure>{table}{SOURCE}{GROWTH_QUADRANT_NOTE}"
        f"{UP_YOY_NOTE if county_name == UP else ''}</div>"
    )
    return html, figures


# Region-wide notes: BLS suppresses some county-industry cells, so U.P. sector
# totals cover only published county figures, and U.P. year-over-year changes
# are computed over counties published in both quarters (data/aggregate_dataframe.py).
UP_LEVEL_NOTE = (
    '<p class="source"><em>U.P. sector totals sum published county figures; '
    'county cells suppressed by BLS are excluded.</em></p>'
)
UP_YOY_NOTE = (
    '<p class="source"><em>U.P. sector totals sum published county figures. '
    'Year-over-year changes use only counties published by BLS in both '
    'quarters, so a county entering or leaving disclosure does not register '
    'as growth or decline.</em></p>'
)


# Wraps the firm-formation and treemap methodology texts in source-note paragraphs.
from components.firm_formation import METHODOLOGY_NOTE as _FIRM_FORMATION_TEXT
FIRM_FORMATION_NOTE = f'<p class="source"><em>{_FIRM_FORMATION_TEXT}</em></p>'

from components.employment_treemap import METHODOLOGY_NOTE as _EMPLOYMENT_TREEMAP_TEXT
EMPLOYMENT_TREEMAP_NOTE = f'<p class="source"><em>{_EMPLOYMENT_TREEMAP_TEXT}</em></p>'


# Builds the Firm Openings & Closings section for one county: a narrative, the
# quarterly establishment-change chart, and a data table. Returns (html, figures).
def build_firm_formation(county_df, county_name, county_id, heading_level=2):
    """Firm Openings & Closings — quarterly establishment churn (industry-level decomposition).

    Gets the per-quarter additions, subtractions, and net from
    get_firm_formation_data. It also tries to load the U.S. national
    benchmark (get_national_qoq_pct of fetch_national_data) and the county's
    prior-quarter establishment counts, and falls back to None for either one
    if loading fails, so the chart degrades to a version without the
    benchmark. The narrative describes the most recent quarter as expanded,
    contracted, or flat. If there is not enough data, it returns a short
    message section and an empty figures dict.
    """
    from components.firm_formation import build_figure as firm_formation_fig
    from data.clean import get_firm_formation_data, get_national_qoq_pct
    from data.fetch import fetch_national_data

    h, _h = f"h{heading_level}", f"/h{heading_level}"
    plot_data = get_firm_formation_data(county_df)
    if plot_data.empty:
        return f'<div class="section"><{h}>Firm Openings &amp; Closings<{_h}><p>Not enough establishment data to compute quarterly churn.</p></div>', {}

    # National benchmark — graceful fallback to 3-trace chart if the fetch fails.
    try:
        national_pct = get_national_qoq_pct(fetch_national_data())
        if national_pct.empty:
            national_pct = None
    except Exception:
        national_pct = None
    try:
        county_prev_estabs = (
            get_total_covered(county_df).set_index("date")["qtrly_estabs"]
            .sort_index().shift(1)
        )
    except Exception:
        county_prev_estabs = None

    latest = plot_data.iloc[-1]
    direction = "expanded" if latest["net"] > 0 else ("contracted" if latest["net"] < 0 else "held flat")
    narrative = (
        f"In the most recent quarter ({latest['year_qtr']}), the county's "
        f"establishment count {direction} by {abs(int(latest['net'])):,} firms — "
        f"the net of {int(latest['additions']):,} added across growing industries "
        f"and {int(abs(latest['subtractions'])):,} lost across shrinking ones."
    )

    fig = firm_formation_fig(plot_data, national_pct, county_prev_estabs)
    div_id = f"{county_id}-firm-formation"
    figures = {div_id: _fig_json(fig)}

    aria = (
        f"Bar chart of quarterly establishment additions and losses in "
        f"{_display_name(county_name)}, with a net-change line overlay."
    )
    table = _data_table_html(
        f"{_display_name(county_name)} — quarterly establishment additions, losses, and net change",
        ["Quarter", "Establishments Added", "Establishments Lost", "Net Change"],
        [
            (
                r["year_qtr"],
                f"{int(r['additions']):+,}",
                f"{int(r['subtractions']):+,}",
                "—" if pd.isna(r["net"]) else f"{int(r['net']):+,}",
            )
            for _, r in plot_data.iterrows()
        ],
    )

    html = (
        f'<div class="section"><{h}>Firm Openings &amp; Closings<{_h}>'
        f'<figure class="chart-figure"><figcaption>{narrative}</figcaption>'
        f"{_chart_div(div_id, aria)}</figure>{table}{SOURCE}{FIRM_FORMATION_NOTE}</div>"
    )
    return html, figures


# ── HTML Assembly ────────────────────────────────────────────────────────────

# Builds the Workforce Composition section for one county: a narrative, the
# treemap with year buttons, and a data table. Returns (html, figures).
def build_employment_treemap(county_df, county_name, county_id, heading_level=2):
    """Workforce Composition — multi-trace treemap with year-selector buttons.

    Gets one snapshot per year from get_treemap_snapshots and draws them as
    separate traces with components.employment_treemap. The narrative names
    the three largest private-sector employers in the latest snapshot. Plotly's
    built-in year menu is removed, and when there is more than one year,
    keyboard-operable HTML buttons (handled by selectTreemapYear in the page
    script) toggle which trace is visible, with the latest year selected by
    default. The data table covers the latest snapshot. If there is no
    disclosable data, it returns a short message section and an empty figures
    dict.
    """
    from components.employment_treemap import build_figure as treemap_fig
    from data.clean import get_treemap_snapshots

    h, _h = f"h{heading_level}", f"/h{heading_level}"
    snapshots = get_treemap_snapshots(county_df)
    if not snapshots:
        return f'<div class="section"><{h}>Workforce Composition<{_h}><p>No disclosable employment data.</p></div>', {}

    year, qtr, latest = snapshots[-1]
    top3 = latest.head(3)
    items = [
        f"{r['industry_label']} ({r['share']*100:.1f}%)"
        for _, r in top3.iterrows()
    ]
    narrative = (
        f"In {year} Q{qtr}, the county's largest private-sector employers are "
        f"{format_industry_list(items)}."
    )

    fig = treemap_fig(snapshots)
    # Plotly's year menu is a non-focusable SVG control (fails WCAG 2.1.1).
    # Strip it and drive the same trace-visibility toggle from real HTML
    # buttons (built below), which are keyboard-operable and expose state.
    # (Assign the property directly — update_layout(updatemenus=[]) merges and
    # would leave the existing menu in place.)
    fig.layout.updatemenus = []
    div_id = f"{county_id}-employment-treemap"
    figures = {div_id: _fig_json(fig)}

    n = len(snapshots)
    default_idx = n - 1
    year_selector = ""
    if n > 1:
        btns = "".join(
            f'<button type="button" class="year-btn" '
            f'aria-pressed="{"true" if i == default_idx else "false"}" '
            f'data-target="{div_id}" data-trace="{i}" data-count="{n}" '
            f'onclick="selectTreemapYear(this)">{yr}</button>'
            for i, (yr, _q, _snap) in enumerate(snapshots)
        )
        year_selector = (
            f'<div class="year-select" role="group" '
            f'aria-label="Select year for the {_display_name(county_name)} workforce treemap">'
            f"{btns}</div>"
        )

    aria = (
        f"Treemap of private-sector employment by industry in {_display_name(county_name)}"
        f", {year} Q{qtr}; rectangle size reflects employment."
    )
    table = _data_table_html(
        f"{_display_name(county_name)} — private employment by industry sector, {year} Q{qtr}",
        ["Sector", "Employment", "Share of Private Workforce", "Establishments",
         "Average Salary"],
        [
            (
                r["industry_label"],
                fmt_number(r["employment"]),
                f'{r["share"] * 100:.1f}%',
                fmt_number(r["qtrly_estabs"]),
                fmt_currency(r["avg_annual_wage"]),
            )
            for _, r in latest.iterrows()
        ],
    )

    html = (
        f'<div class="section"><{h}>Workforce Composition<{_h}>'
        f'<figure class="chart-figure"><figcaption>{narrative}</figcaption>'
        f"{_chart_div(div_id, aria)}{year_selector}</figure>"
        f"{table}{SOURCE}{EMPLOYMENT_TREEMAP_NOTE}"
        f"{UP_LEVEL_NOTE if county_name == UP else ''}</div>"
    )
    return html, figures

# Source line shown under the housing section.
HOUSING_SOURCE = (
    '<p class="source">Source: <a href="https://www.census.gov/programs-surveys/acs">'
    'U.S. Census Bureau ACS</a> — Annual</p>'
)


# Loads the Census housing data once per build so every county page reuses it.
@lru_cache(maxsize=1)
def _housing_df():
    """Call get_up_housing() on first use and cache the result with lru_cache.

    If the load fails it prints a warning and returns an empty DataFrame, so
    the build still finishes and each county's housing section shows its
    "no data" message instead of crashing the whole publish.
    """
    from data.fetch_Census_housing import get_up_housing
    try:
        return get_up_housing()
    except Exception as e:
        print(f"WARNING: housing data could not be loaded: {e}", file=sys.stderr)
        return pd.DataFrame()


# Builds the Housing Median Value section for one county: a narrative, the
# time-series chart, and a data table. Returns (html, figures).
def build_housing_trends(county_df, county_name, county_id, heading_level=2):
    """Housing Median Value Trends: Census ACS median home value by year.

    Takes the same arguments as the QCEW builders so it fits SECTION_BUILDERS,
    but ignores county_df and filters the cached housing DataFrame to
    county_name instead. The narrative comes from
    narrate_median_house_value_trends, the same function the Streamlit app
    uses, called with the first and last years that have a median value. The
    figure comes from components.housing_median_value_tseries.build_figure.
    If the county has no housing rows, it returns a short message section and
    an empty figures dict.
    """
    from components.housing_median_value_tseries import build_figure as build_housing_median_value_fig

    h, _h = f"h{heading_level}", f"/h{heading_level}"
    title = "Housing Median Value Trends"
    empty = f'<div class="section"><{h}>{title}<{_h}><p>No housing data available.</p></div>', {}

    housing = _housing_df()
    if housing.empty or "county_name" not in housing.columns:
        return empty

    rows = housing[housing["county_name"] == county_name].sort_values("year")
    rows = rows[rows["median_home_value"].notna()]
    if rows.empty:
        return empty

    first, last = rows.iloc[0], rows.iloc[-1]
    y0, y1 = int(first["year"]), int(last["year"])
    narrative = narrate_median_house_value_trends(
        county_name=county_name,
        start_year=y0, end_year=y1,
        start_value=first["median_home_value"],
        end_value=last["median_home_value"],
    )

    fig = build_housing_median_value_fig(rows)
    div_id = f"{county_id}-housing-median-value"
    figures = {div_id: _fig_json(fig)}

    aria = f"Line chart of median home value in {_display_name(county_name)}, {y0} to {y1}."
    table = _data_table_html(
        f"{_display_name(county_name)} — median home value by year",
        ["Year", "Median Home Value"],
        [(int(r["year"]), fmt_currency(r["median_home_value"])) for _, r in rows.iterrows()],
    )

    html = (
        f'<div class="section"><{h}>{title}<{_h}>'
        f'<figure class="chart-figure"><figcaption>{narrative}</figcaption>'
        f"{_chart_div(div_id, aria)}</figure>{table}{HOUSING_SOURCE}{HOUSING_NOTE}</div>"
    )
    return html, figures


def build_ai_risk_score(mit_ai_risk_merged_df, county_name, county_id, heading_level=2):
    from components.county_AI_risk_score import (
        build_figure as ai_risk_figure,
        get_county_risk_data,
    )

    h, _h = f"h{heading_level}", f"/h{heading_level}"
    county_data = get_county_risk_data(mit_ai_risk_merged_df, county_name)
    title = "AI Vulnerability by Sector"
    if county_data.empty:
        return (
            f'<div class="section"><{h}>{title}<{_h}>'
            f'<p>No AI vulnerability rating data is available for '
            f'{_display_name(county_name)}.</p></div>',
            {},
        )

    total_workers = county_data["number_of_workers"].sum()
    weighted_average = county_data["weighted_score"].sum() / total_workers
    narrative = (
        f"Across {len(county_data)} rated sectors, the employment-weighted "
        f"average AI vulnerability score is {weighted_average:.2f} out of 5, "
        f"representing {fmt_number(total_workers)} workers."
    )

    div_id = f"{county_id}-ai-risk-score"
    fig = ai_risk_figure(county_data, _display_name(county_name), weighted_average)
    figures = {div_id: _fig_json(fig)}
    aria = (
        f"Histogram of workers by AI vulnerability score for {_display_name(county_name)} "
        f"across {len(county_data)} rated sectors. A dashed vertical "
        f"line marks the employment-weighted average score of "
        f"{weighted_average:.2f} out of 5."
    )
    table = _data_table_html(
        f"{_display_name(county_name)} — sector AI vulnerability scores and workers",
        ["Sector", "Vulnerability Score", "Workers", "Weighted Score Contribution"],
        [
            (
                AI_TARGET_DISPLAY_LABELS.get(row["target_code"], row["target_code"]),
                f'{row["risk_score"]:.2f}',
                fmt_number(row["number_of_workers"]),
                fmt_number(row["weighted_score"]),
            )
            for _, row in county_data.sort_values("target_code").iterrows()
        ],
    )
    source = (
        '<p class="source">Sector vulnerability ratings: '
        '<a href="https://airisk.mit.edu/navigator#/taxonomies">MIT AI Risk '
        'Navigator</a>. Employment: latest published BLS QCEW quarter.</p>'
        f'<p class="source"><em>{AI_SECTOR_FOOTNOTE}</em></p>'
    )
    html = (
        f'<div class="section"><{h}>{title}<{_h}>'
        f'<figure class="chart-figure"><figcaption>{narrative}</figcaption>'
        f'{_chart_div(div_id, aria)}</figure>{table}{source}</div>'
    )
    return html, figures


# Lists the five per-county sections in display order. Both the detail tabs in
# index.html and the standalone embeds loop over this list.
# (slug, builder) pairs — the slug is used as the embed filename under
# docs/embeds/<county>/<slug>.html.
SECTION_BUILDERS = [
    ("trends", build_trends),
    ("housing-median-value", build_housing_trends),
    ("workforce-composition", build_employment_treemap),
    ("industry-landscape", build_growth_quadrant),
    ("firm-formation", build_firm_formation),
]


def _section_builders(mit_ai_risk_merged_df):
    def build_county_ai_risk(_county_df, county_name, county_id, heading_level=2):
        return build_ai_risk_score(
            mit_ai_risk_merged_df, county_name, county_id, heading_level
        )

    builders = SECTION_BUILDERS.copy()
    builders.insert(3, ("ai-risk-score", build_county_ai_risk))
    return builders


def build_html(df, housing_df, mit_ai_risk_merged_df=None):
    """Assemble the complete static HTML dashboard."""
    from data.fetch_fred import fetch_real_gdp, fetch_unemployment_rate
    from data.fetch_irs_migration import fetch_irs_migration
    from data.clean import (
        latest_gdp_with_growth, latest_unrate_with_yoy, latest_irs_net,
    )
    aggregate_df = get_aggregate_data(df)
    figures = {}
    if mit_ai_risk_merged_df is None:
        mit_ai_risk_merged_df = _load_ai_risk_data(df)
    section_builders = _section_builders(mit_ai_risk_merged_df)

    # Data quarter badge
    sample_totals = get_total_covered(df)
    sample_latest = get_latest_quarter(sample_totals)
    if not sample_latest.empty:
        r = sample_latest.iloc[0]
        badge = f"Data as of {int(r['year'])} Q{int(r['qtr'])}"
    else:
        badge = "Data unavailable"

    # Load secondary KPI datasets once (cache-hot after first run; each loader
    # returns empty on missing key/network failure → cells degrade to "—").
    df_gdp_secondary = fetch_real_gdp()
    df_unrate_secondary = fetch_unemployment_rate()
    df_irs_secondary = fetch_irs_migration()

    # ── Front-page visuals: interactive county map + largest-county comparison
    from components.county_map import build_figure as _map_fig, _load_geojson
    from components.top_counties import build_figure as _top_fig, get_top_counties
    from data.clean import latest_county_summaries

    summary = latest_county_summaries(df)
    geojson = _load_geojson()
    if not summary.empty and geojson is not None:
        benchmarks = _load_benchmarks(summary)
        figures["up-county-map"] = _fig_json(_map_fig(summary, geojson, benchmarks))
        map_aria = (
            "Choropleth map of the 15 Upper Peninsula counties shaded by "
            "year-over-year employment growth, with small inset maps of Michigan "
            "and the United States giving statewide and national totals."
        )
        map_html = (
            '<div class="section"><h2>Upper Peninsula at a Glance</h2>'
            '<figure class="chart-figure"><figcaption>Counties are shaded by '
            'year-over-year employment growth (latest published QCEW quarter). '
            'Hover any county for its employment, establishment count, and average '
            'salary. Hover the small U.S. and Michigan maps for national and '
            'statewide totals; both also appear at the bottom of the data table.'
            '</figcaption>'
            f'{_chart_div("up-county-map", map_aria)}</figure>'
            f'{_map_table_html(summary, benchmarks)}{SOURCE}</div>'
        )
    else:
        map_html = (
            '<div class="section"><h2>Upper Peninsula at a Glance</h2>'
            '<p>County map unavailable.</p></div>'
        )

    top = get_top_counties(df)
    if not top.empty:
        figures["up-top-counties"] = _fig_json(_top_fig(top))
        top_aria = (
            "Grouped bar chart comparing year-over-year employment, establishment, "
            "and wage growth for the five largest Upper Peninsula county economies."
        )
        top_html = (
            '<div class="section"><h2>Largest County Economies</h2>'
            '<figure class="chart-figure"><figcaption>The five UP counties with the '
            'most covered employment, compared on year-over-year growth in jobs, '
            'businesses, and wages.</figcaption>'
            f'{_chart_div("up-top-counties", top_aria)}</figure>'
            f'{_top_table_html(top)}{SOURCE}</div>'
        )
    else:
        top_html = (
            '<div class="section"><h2>Largest County Economies</h2>'
            '<p>No disclosable county totals available.</p></div>'
        )

    # ── Per-county detail tabs (KPI card + four chart sections each), limited
    # to the largest county economies.
    tab_buttons = ""
    tab_content = ""   
    for idx, county_name in enumerate(_detail_locations(df)):
        if county_name == "Upper Peninsula":
            county_df = aggregate_df
        else:
            county_df = df[df["county_name"] == county_name]
        county_id = county_name.lower().replace(" ", "-")
        active = " active" if idx == 0 else ""
        color = COUNTY_COLORS.get(county_name, FAU_BLUE)
        secondary = _secondary_for(
            county_name, df_gdp_secondary, df_unrate_secondary, df_irs_secondary
        )
        display = _display_name(county_name)
        tab_buttons += (
            f'<button class="tab-btn{active}" data-tab="{county_id}" '
            f'aria-pressed="{"true" if idx == 0 else "false"}" '
            f'aria-controls="{county_id}" '
            f"onclick=\"showTab('{county_id}')\">{display}</button>\n"
        )

        sections = [
            f'<div class="snapshot-row single-county">'
            f'{build_kpi_card(county_df, county_name, color, secondary, housing_df)}</div>',
            KPI_CAPTION_HTML,
        ]
        for _slug, builder in section_builders:
            sections.append('<div class="divider"></div>')
            # Index detail sections sit under the h3 county name, itself under the
            # h2 "County Detail" — so they must be h4 to keep the hierarchy nested
            # (WCAG 1.3.1). Standalone embeds keep the default h2 (under their h1).
            section_html, section_figs = builder(
                county_df, county_name, county_id, heading_level=4
            )
            sections.append(section_html)
            figures.update(section_figs)

        tab_content += f'<div id="{county_id}" class="tab-content{active}">\n'
        tab_content += "\n".join(sections)
        tab_content += "\n</div>\n"

    figures_json = json.dumps(figures)
    built = datetime.now(timezone.utc).strftime("%B %d, %Y")

    # Assemble HTML — CSS and JS are regular strings (no f-string escaping needed)
    return "\n".join([
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        "<title>Upper Peninsula Regional Economic Report</title>",
        '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>',
        "<style>",
        CSS,
        "</style>",
        "</head>",
        "<body>",
        "<header>",
        '<h1 class="main-title">Upper Peninsula Regional Economic Report</h1>',
        '<p class="main-subtitle">Quarterly Census of Employment and Wages (QCEW) &mdash; '
        'the 15 counties of Michigan&rsquo;s Upper Peninsula</p>',
        f'<div class="data-badge">{badge}</div>',
        "</header>",
        map_html,
        '<div class="divider"></div>',
        top_html,
        '<div class="divider"></div>',
        f'<h2 style="color: {FAU_BLUE};">County Detail</h2>',
        f'<div class="tab-bar" role="group" aria-label="Select a county">{tab_buttons}</div>',
        tab_content,
        '<footer class="footer">',
        f'Source: <a href="https://www.bls.gov/cew/">BLS QCEW</a> &mdash; Quarterly '
        f'| Last updated: {built}',
        "</footer>",
        "<script>",
        f"var figureData = {figures_json};",
        JS,
        "</script>",
        "</body>",
        "</html>",
    ])


# ── Embed pipeline ───────────────────────────────────────────────────────────

KPI_CAPTION_HTML = (
    '<p class="kpi-caption">'
    'Net Migration reflects IRS SOI county-to-county filings (Total Migration-US '
    'and Foreign) — the net change in tax-filer exemptions between consecutive '
    'filing years, inclusive of moves into and out of the country. FRED real GDP '
    'and unemployment rate vintages reflect the most recent BEA/BLS releases as '
    'of the data badge above.'
    '</p>'
)


def write_embeds(df, housing_df, mit_ai_risk_merged_df=None):
    """Emit standalone embed pages: the region overview visuals plus per-county
    KPI cards and chart sections for the largest county economies.

    File layout:
        docs/embeds/up-map.html              (interactive county choropleth)
        docs/embeds/up-top-counties.html     (largest-county growth comparison)
        docs/embeds/kpi-<county-slug>.html   (one per detail county)
        docs/embeds/<county-slug>/<section-slug>.html  (4 per detail county)

    Each output is a self-contained HTML page wrapping the same fragments
    used by the main dashboard — so visuals stay identical and the weekly
    GitHub Action regenerates them on the same cadence as docs/index.html.
    """
    from data.fetch_fred import fetch_real_gdp, fetch_unemployment_rate
    from data.fetch_irs_migration import fetch_irs_migration
    from data.clean import (
        latest_gdp_with_growth, latest_unrate_with_yoy, latest_irs_net,
        latest_county_summaries,
    )
    from components.county_map import build_figure as _map_fig, _load_geojson
    from components.top_counties import build_figure as _top_fig, get_top_counties

    embeds_dir = DOCS_DIR / "embeds"
    embeds_dir.mkdir(parents=True, exist_ok=True)
    if mit_ai_risk_merged_df is None:
        mit_ai_risk_merged_df = _load_ai_risk_data(df)
    section_builders = _section_builders(mit_ai_risk_merged_df)

    df_gdp = fetch_real_gdp()
    df_unrate = fetch_unemployment_rate()
    df_irs = fetch_irs_migration()

    # ── Region overview embeds: interactive map + largest-county comparison. ─
    summary = latest_county_summaries(df)
    geojson = _load_geojson()
    if not summary.empty and geojson is not None:
        benchmarks = _load_benchmarks(summary)
        map_aria = (
            "Choropleth map of the 15 Upper Peninsula counties shaded by "
            "year-over-year employment growth, with small inset maps of Michigan "
            "and the United States giving statewide and national totals."
        )
        map_body = (
            '<div class="section"><h2>Upper Peninsula at a Glance</h2>'
            '<figure class="chart-figure"><figcaption>Counties shaded by '
            'year-over-year employment growth (latest published QCEW quarter). '
            'Hover the small U.S. and Michigan maps for national and statewide '
            'totals; both also appear at the bottom of the data table.'
            '</figcaption>'
            f'{_chart_div("up-county-map", map_aria)}</figure>'
            f'{_map_table_html(summary, benchmarks)}</div>'
        )
        (embeds_dir / "up-map.html").write_text(
            wrap_as_embed(
                map_body, {"up-county-map": _fig_json(_map_fig(summary, geojson, benchmarks))},
                "Upper Peninsula — County Map",
            ),
            encoding="utf-8",
        )

    top = get_top_counties(df)
    if not top.empty:
        top_aria = (
            "Grouped bar chart comparing year-over-year employment, establishment, "
            "and wage growth for the five largest Upper Peninsula county economies."
        )
        top_body = (
            '<div class="section"><h2>Largest County Economies</h2>'
            '<figure class="chart-figure"><figcaption>The five UP counties with the '
            'most covered employment, compared on year-over-year growth in jobs, '
            'businesses, and wages.</figcaption>'
            f'{_chart_div("up-top-counties", top_aria)}</figure>'
            f'{_top_table_html(top)}</div>'
        )
        (embeds_dir / "up-top-counties.html").write_text(
            wrap_as_embed(
                top_body, {"up-top-counties": _fig_json(_top_fig(top))},
                "Upper Peninsula — Largest County Economies",
            ),
            encoding="utf-8",
        )

    # ── Per-county KPI + chart embeds for the largest county economies. ──────
    aggregate_df = get_aggregate_data(df)
    order = _detail_locations(df)
    for county_name in order:
        county_df = (aggregate_df if county_name == "Upper Peninsula"
                 else df[df["county_name"] == county_name])
        county_id = county_name.lower().replace(" ", "-")
        color = COUNTY_COLORS.get(county_name, FAU_BLUE)
        secondary = _secondary_for(county_name, df_gdp, df_unrate, df_irs)
        card_html = build_kpi_card(county_df, county_name, color, secondary, housing_df)
        body = (
            f'<h2 style="color: {FAU_BLUE}; margin-bottom: 0.5rem;">'
            f'{_display_name(county_name)} Snapshot</h2>'
            f'<div class="snapshot-row single-county">{card_html}</div>'
            f'{KPI_CAPTION_HTML}'
        )
        (embeds_dir / f"kpi-{county_id}.html").write_text(
            wrap_as_embed(body, {}, f"{_display_name(county_name)} — KPI Snapshot"),
            encoding="utf-8",
        )

        county_dir = embeds_dir / county_id
        county_dir.mkdir(parents=True, exist_ok=True)
        for slug, builder in section_builders:
            section_html, section_figs = builder(county_df, county_name, county_id)
            title = f"{_display_name(county_name)} — {slug.replace('-', ' ').title()}"
            (county_dir / f"{slug}.html").write_text(
                wrap_as_embed(section_html, section_figs, title),
                encoding="utf-8",
            )

    print(
        f"  Wrote 2 overview embeds + {len(order)} KPI embeds + "
        f"{len(order) * len(section_builders)} chart embeds to {embeds_dir}"
    )


from data.fetch_Census_housing import get_up_housing

def _load_housing():
    """Census housing data; an empty DataFrame (cells show '—') on any failure."""
    try:
        return get_up_housing()
    except Exception as exc:  # must never break the build
        print(f"WARNING: housing data unavailable ({exc}); housing KPI/chart will be blank")
        return pd.DataFrame()

from data.fetch_Census_housing import get_up_housing

def _load_housing():
    """Census housing data; an empty DataFrame (cells show '—') on any failure."""
    try:
        return get_up_housing()
    except Exception as exc:  # must never break the build
        print(f"WARNING: housing data unavailable ({exc}); housing KPI/chart will be blank")
        return pd.DataFrame()

# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Loading QCEW data...")
    raw = fetch_all_data()
    if raw.empty:
        print("ERROR: No data available. Check your internet connection.")
        sys.exit(1)

    df = clean(raw)
    print(f"  {len(df):,} rows for {df['county_name'].nunique()} counties")

    # The QCEW build no longer gates on FRED. fetch_real_gdp/_unemployment_rate
    # fetch fresh and fall back to the committed last-good cache on failure (see
    # data/fetch_fred._fetch_with_cache_fallback), so a FRED rate-limit or outage
    # leaves last week's KPI row in place rather than blanking it or aborting the
    # whole publish. We log a heads-up if a key is set but both fetches come back
    # empty (fresh fetch failed AND no fallback cache) — the secondary row then
    # degrades to "—" — but we still publish the fresh QCEW data.
    from data.fetch_fred import (
        fred_key_configured, fetch_real_gdp, fetch_unemployment_rate,
    )
    if fred_key_configured():
        empty = [
            name
            for name, frame in (
                ("Real GDP", fetch_real_gdp()),
                ("unemployment", fetch_unemployment_rate()),
            )
            if frame.empty
        ]
        if empty:
            print(
                f"WARNING: FRED_API_KEY is set but the {' and '.join(empty)} "
                "fetch returned no data and no fallback cache exists; the "
                "secondary KPI row will show '—'. Publishing fresh QCEW data."
            )
    housing_df = _load_housing()
    print("Building HTML dashboard...")
    mit_ai_risk_merged_df = _load_ai_risk_data(raw)
    html = build_html(df, housing_df, mit_ai_risk_merged_df)

    DOCS_DIR.mkdir(exist_ok=True)
    output = DOCS_DIR / "index.html"
    output.write_text(html, encoding="utf-8")
    print(f"Done! {output} ({output.stat().st_size / 1024:.0f} KB)")

    print("Building embed pages...")
    write_embeds(df,housing_df, mit_ai_risk_merged_df)