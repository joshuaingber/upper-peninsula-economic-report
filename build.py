#!/usr/bin/env python3
"""
Build static HTML dashboard from QCEW data for GitHub Pages.

Reuses the existing data pipeline (data/fetch.py, data/clean.py) and
recreates all Plotly charts from the Streamlit app as a self-contained
docs/index.html with embedded JSON figure data rendered by Plotly.js.

Usage:
    python build.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from data.fetch import fetch_all_data
from data.clean import (
    clean, get_total_covered, get_latest_quarter, get_growth_quadrant_data,
)
from data.analysis import deseasonalize_trend, project_trend, periods_to_current_quarter
from components.growth_quadrant import (
    build_figure as build_growth_quadrant_fig,
    METHODOLOGY_NOTE as _GROWTH_QUADRANT_TEXT,
)
GROWTH_QUADRANT_NOTE = f'<p class="source"><em>{_GROWTH_QUADRANT_TEXT}</em></p>'
from data.constants import (
    FAU_BLUE, FAU_RED, FAU_DARK_GRAY, FAU_GRAY,
    FAU_ELECTRIC_BLUE, FAU_SKY_BLUE, COUNTY_COLORS, COUNTIES,
    NMU_FONT_FAMILY, GOOGLE_FONTS_IMPORT, PLOTLY_FONT,
)
from utils.formatting import fmt_number, fmt_currency, fmt_pct
from utils.narratives import narrate_employment_trends, format_industry_list

DOCS_DIR = Path(__file__).parent / "docs"
MIN_EMPLOYMENT = 100

# Per-county deep dives are generated for the N largest county economies (by
# latest employment). All 15 counties × 4 sections would be 60 embeds and an
# unwieldy 15-tab strip; the largest five keep the static build and the
# iframe set manageable while covering the bulk of UP employment.
DETAIL_COUNTY_N = 5


def _detail_counties(df) -> list[str]:
    """Names of the N largest UP county economies for per-county detail/embeds."""
    from components.top_counties import get_top_counties
    top = get_top_counties(df, DETAIL_COUNTY_N)
    if not top.empty:
        return top["county_name"].tolist()
    return list(COUNTIES.values())[:DETAIL_COUNTY_N]

# ── CSS ──────────────────────────────────────────────────────────────────────

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
.tab-bar { display: flex; border-bottom: 2px solid """ + FAU_GRAY + """; margin: 1.5rem 0 0 0; }
.tab-btn {
    padding: 0.75rem 1.5rem;
    font-weight: 500;
    color: """ + FAU_DARK_GRAY + """;
    background: none;
    border: none;
    cursor: pointer;
    font-size: 1rem;
    border-bottom: 3px solid transparent;
    margin-bottom: -2px;
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
    .tab-btn { padding: 0.5rem 1rem; font-size: 0.9rem; }
}
"""

# ── JavaScript ───────────────────────────────────────────────────────────────

JS = """
function showTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(function(el) { el.classList.remove('active'); });
    document.querySelectorAll('.tab-btn').forEach(function(el) { el.classList.remove('active'); });
    document.getElementById(tabId).classList.add('active');
    document.querySelector('[data-tab="' + tabId + '"]').classList.add('active');
    setTimeout(function() {
        document.querySelectorAll('#' + tabId + ' .plotly-chart').forEach(function(el) {
            if (el.data) Plotly.Plots.resize(el);
        });
    }, 50);
}

Object.keys(figureData).forEach(function(divId) {
    var fig = figureData[divId];
    Plotly.newPlot(divId, fig.data, fig.layout, {responsive: true});
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
"""

# Each embed posts its rendered height to the parent host page via postMessage.
# Debounce (100 ms) + last-height dedupe kill the feedback loop where Plotly's
# responsive: true would re-fire layout when the parent resizes the iframe.
EMBED_JS = """
Object.keys(figureData).forEach(function(divId) {
    var fig = figureData[divId];
    Plotly.newPlot(divId, fig.data, fig.layout, {responsive: true});
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


def wrap_as_embed(body_html: str, figures: dict, page_title: str) -> str:
    """Wrap a body HTML fragment into a self-contained embed page.

    Each embed is a standalone HTML document: loads Plotly from CDN, bundles
    the trimmed embed CSS, renders the included figures, and posts its content
    height to the parent via postMessage. CSS isolation is automatic — iframes
    have their own document, so styles cannot collide with the host page.
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
        body_html,
        "<script>",
        f"var figureData = {figures_json};",
        EMBED_JS,
        "</script>",
        "</body>",
        "</html>",
    ])


# ── Helpers ──────────────────────────────────────────────────────────────────

SOURCE = '<p class="source">Source: <a href="https://www.bls.gov/cew/">BLS QCEW</a> — Quarterly</p>'
TRENDS_NOTE = (
    '<p class="source"><em>Chart shows the STL trend (raw quarterly values omitted '
    'for clarity). Trend computed via STL decomposition (period=4, robust); salary '
    'on log scale. Projection extrapolates a linear fit through the last 4 trend '
    'points to the current calendar quarter — the horizon shrinks as new QCEW data '
    'is published. BLS does not publish seasonally adjusted QCEW — this is a custom '
    'estimate.</em></p>'
)


def _fig_json(fig):
    """Convert a Plotly figure to a JSON-serializable dict."""
    return json.loads(fig.to_json())


def _delta_html(pct):
    """Render a YoY percent-change badge."""
    if pd.isna(pct):
        return ""
    css = "positive" if pct >= 0 else "negative"
    arrow = "&#9650;" if pct >= 0 else "&#9660;"
    return f'<div class="kpi-delta {css}">{arrow} {abs(pct):.1f}% YoY</div>'


# ── KPI Card ─────────────────────────────────────────────────────────────────

def _secondary_row_html(secondary):
    """Build the second KPI row HTML — Real GDP, Unemployment, Net Migration."""
    secondary = secondary or {}
    gdp = secondary.get("gdp") or {}
    unr = secondary.get("unrate") or {}
    irs = secondary.get("irs") or {}

    if gdp:
        gdp_value = f"${gdp['value_billions']:.1f}B"
        growth = gdp["yoy_growth"]
        arrow = "&#9650;" if growth >= 0 else "&#9660;"
        cls = "positive" if growth >= 0 else "negative"
        gdp_delta = f'<div class="kpi-delta {cls}">{arrow} {abs(growth)*100:.1f}% YoY</div>'
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
        unr_delta = f'<div class="kpi-delta {cls}">{arrow} {abs(delta):.1f}pp YoY</div>'
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
        f'<div class="kpi-item"><div class="kpi-label">Unemployment rate</div>'
        f'<div class="kpi-value">{unr_value}</div>{unr_delta}{unr_period}</div>'
        f'<div class="kpi-item"><div class="kpi-label">Net Migration</div>'
        f'<div class="kpi-value">{irs_value}</div>{irs_delta}{irs_period}</div>'
        f'</div>'
    )


def build_kpi_card(county_df, county_name, color, secondary=None):
    """Generate HTML for one county KPI card (primary + optional secondary row)."""
    totals = get_total_covered(county_df)
    latest = get_latest_quarter(totals)

    if latest.empty:
        return (
            f'<div class="county-card" style="border-left-color: {color};">'
            f'<h3 style="color: {color};">{county_name} County</h3>'
            f'<p>No data available.</p></div>'
        )

    row = latest.iloc[0]
    secondary_html = _secondary_row_html(secondary)
    return (
        f'<div class="county-card" style="border-left-color: {color};">'
        f'<h3 style="color: {color};">{county_name} County</h3>'
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
        f'</div>{secondary_html}</div>'
    )


# ── Section Builders ─────────────────────────────────────────────────────────
# Each function builds Plotly figures, adds them to `figures` dict,
# and returns the HTML for that dashboard section.

def _trends_chart(totals, y_col, title, color, tickformat, hover_prefix, log_transform):
    """Side-by-side STL-trend chart with linear projection through the current quarter."""
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


def build_trends(county_df, county_name, county_id):
    """Employment & Salary Trends — raw + STL-trend overlays, side by side.

    Returns (html_fragment, figures_dict) so the caller can either merge the
    figures into the main dashboard's master dict (index.html path) or write
    the fragment as a standalone embed page.
    """
    totals = get_total_covered(county_df)
    if totals.empty:
        return '<div class="section"><h2>Employment &amp; Salary Trends</h2><p>No trend data available.</p></div>', {}

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

    html = (
        f'<div class="section"><h2>Employment &amp; Salary Trends</h2>'
        f'<p>{narrative}</p>'
        f'<div class="chart-row">'
        f'<div class="chart-col"><div id="{eid}" class="plotly-chart"></div></div>'
        f'<div class="chart-col"><div id="{wid}" class="plotly-chart"></div></div>'
        f'</div>{SOURCE}{TRENDS_NOTE}</div>'
    )
    return html, figures


def build_growth_quadrant(county_df, county_name, county_id):
    """Growth Quadrant — YoY employment vs salary growth, domain-colored bubbles."""
    plot_data = get_growth_quadrant_data(county_df)
    if plot_data.empty:
        return '<div class="section"><h2>Industry Landscape</h2><p>No disclosable industry growth data.</p></div>', {}

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

    html = (
        f'<div class="section"><h2>Industry Landscape</h2>'
        f'<p>{narrative}</p>'
        f'<div id="{div_id}" class="plotly-chart"></div>{SOURCE}{GROWTH_QUADRANT_NOTE}</div>'
    )
    return html, figures


from components.firm_formation import METHODOLOGY_NOTE as _FIRM_FORMATION_TEXT
FIRM_FORMATION_NOTE = f'<p class="source"><em>{_FIRM_FORMATION_TEXT}</em></p>'

from components.employment_treemap import METHODOLOGY_NOTE as _EMPLOYMENT_TREEMAP_TEXT
EMPLOYMENT_TREEMAP_NOTE = f'<p class="source"><em>{_EMPLOYMENT_TREEMAP_TEXT}</em></p>'


def build_firm_formation(county_df, county_name, county_id):
    """Firm Openings & Closings — quarterly establishment churn (industry-level decomposition)."""
    from components.firm_formation import build_figure as firm_formation_fig
    from data.clean import get_firm_formation_data, get_national_qoq_pct
    from data.fetch import fetch_national_data

    plot_data = get_firm_formation_data(county_df)
    if plot_data.empty:
        return '<div class="section"><h2>Firm Openings &amp; Closings</h2><p>Not enough establishment data to compute quarterly churn.</p></div>', {}

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

    html = (
        f'<div class="section"><h2>Firm Openings &amp; Closings</h2>'
        f'<p>{narrative}</p>'
        f'<div id="{div_id}" class="plotly-chart"></div>{SOURCE}{FIRM_FORMATION_NOTE}</div>'
    )
    return html, figures


# ── HTML Assembly ────────────────────────────────────────────────────────────

def build_employment_treemap(county_df, county_name, county_id):
    """Workforce Composition — multi-trace treemap with year-selector buttons."""
    from components.employment_treemap import build_figure as treemap_fig
    from data.clean import get_treemap_snapshots

    snapshots = get_treemap_snapshots(county_df)
    if not snapshots:
        return '<div class="section"><h2>Workforce Composition</h2><p>No disclosable employment data.</p></div>', {}

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
    div_id = f"{county_id}-employment-treemap"
    figures = {div_id: _fig_json(fig)}

    html = (
        f'<div class="section"><h2>Workforce Composition</h2>'
        f'<p>{narrative}</p>'
        f'<div id="{div_id}" class="plotly-chart"></div>{SOURCE}{EMPLOYMENT_TREEMAP_NOTE}</div>'
    )
    return html, figures


# (slug, builder) pairs — the slug is used as the embed filename under
# docs/embeds/<county>/<slug>.html.
SECTION_BUILDERS = [
    ("trends", build_trends),
    ("workforce-composition", build_employment_treemap),
    ("industry-landscape", build_growth_quadrant),
    ("firm-formation", build_firm_formation),
]


def build_html(df):
    """Assemble the complete static HTML dashboard."""
    from data.fetch_fred import fetch_real_gdp, fetch_unemployment_rate
    from data.fetch_irs_migration import fetch_irs_migration
    from data.clean import (
        latest_gdp_with_growth, latest_unrate_with_yoy, latest_irs_net,
    )

    figures = {}

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
        figures["up-county-map"] = _fig_json(_map_fig(summary, geojson))
        map_html = (
            '<div class="section"><h2>Upper Peninsula at a Glance</h2>'
            '<p>Counties are shaded by year-over-year employment growth (latest '
            'published QCEW quarter). Hover any county for its employment, '
            'establishment count, and average salary.</p>'
            '<div id="up-county-map" class="plotly-chart"></div>'
            f'{SOURCE}</div>'
        )
    else:
        map_html = (
            '<div class="section"><h2>Upper Peninsula at a Glance</h2>'
            '<p>County map unavailable.</p></div>'
        )

    top = get_top_counties(df)
    if not top.empty:
        figures["up-top-counties"] = _fig_json(_top_fig(top))
        top_html = (
            '<div class="section"><h2>Largest County Economies</h2>'
            '<p>The five UP counties with the most covered employment, compared on '
            'year-over-year growth in jobs, businesses, and wages.</p>'
            '<div id="up-top-counties" class="plotly-chart"></div>'
            f'{SOURCE}</div>'
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
    for idx, county_name in enumerate(_detail_counties(df)):
        county_df = df[df["county_name"] == county_name]
        county_id = county_name.lower().replace(" ", "-")
        active = " active" if idx == 0 else ""
        color = COUNTY_COLORS.get(county_name, FAU_BLUE)
        secondary = {
            "gdp": latest_gdp_with_growth(df_gdp_secondary, county_name),
            "unrate": latest_unrate_with_yoy(df_unrate_secondary, county_name),
            "irs": latest_irs_net(df_irs_secondary, county_name),
        }

        tab_buttons += (
            f'<button class="tab-btn{active}" data-tab="{county_id}" '
            f"onclick=\"showTab('{county_id}')\">{county_name} County</button>\n"
        )

        sections = [
            f'<div class="snapshot-row single-county">'
            f'{build_kpi_card(county_df, county_name, color, secondary)}</div>',
            KPI_CAPTION_HTML,
        ]
        for _slug, builder in SECTION_BUILDERS:
            sections.append('<div class="divider"></div>')
            section_html, section_figs = builder(county_df, county_name, county_id)
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
        f'<h3 style="color: {FAU_BLUE};">County Detail</h3>',
        f'<div class="tab-bar">{tab_buttons}</div>',
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


def write_embeds(df):
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

    df_gdp = fetch_real_gdp()
    df_unrate = fetch_unemployment_rate()
    df_irs = fetch_irs_migration()

    # ── Region overview embeds: interactive map + largest-county comparison. ─
    summary = latest_county_summaries(df)
    geojson = _load_geojson()
    if not summary.empty and geojson is not None:
        map_body = (
            '<div class="section"><h2>Upper Peninsula at a Glance</h2>'
            '<div id="up-county-map" class="plotly-chart"></div></div>'
        )
        (embeds_dir / "up-map.html").write_text(
            wrap_as_embed(
                map_body, {"up-county-map": _fig_json(_map_fig(summary, geojson))},
                "Upper Peninsula — County Map",
            ),
            encoding="utf-8",
        )

    top = get_top_counties(df)
    if not top.empty:
        top_body = (
            '<div class="section"><h2>Largest County Economies</h2>'
            '<div id="up-top-counties" class="plotly-chart"></div></div>'
        )
        (embeds_dir / "up-top-counties.html").write_text(
            wrap_as_embed(
                top_body, {"up-top-counties": _fig_json(_top_fig(top))},
                "Upper Peninsula — Largest County Economies",
            ),
            encoding="utf-8",
        )

    # ── Per-county KPI + chart embeds for the largest county economies. ──────
    order = _detail_counties(df)
    for county_name in order:
        county_df = df[df["county_name"] == county_name]
        county_id = county_name.lower().replace(" ", "-")
        color = COUNTY_COLORS.get(county_name, FAU_BLUE)
        secondary = {
            "gdp": latest_gdp_with_growth(df_gdp, county_name),
            "unrate": latest_unrate_with_yoy(df_unrate, county_name),
            "irs": latest_irs_net(df_irs, county_name),
        }
        card_html = build_kpi_card(county_df, county_name, color, secondary)
        body = (
            f'<h3 style="color: {FAU_BLUE}; margin-bottom: 0.5rem;">'
            f'{county_name} County Snapshot</h3>'
            f'<div class="snapshot-row single-county">{card_html}</div>'
            f'{KPI_CAPTION_HTML}'
        )
        (embeds_dir / f"kpi-{county_id}.html").write_text(
            wrap_as_embed(body, {}, f"{county_name} County — KPI Snapshot"),
            encoding="utf-8",
        )

        county_dir = embeds_dir / county_id
        county_dir.mkdir(parents=True, exist_ok=True)
        for slug, builder in SECTION_BUILDERS:
            section_html, section_figs = builder(county_df, county_name, county_id)
            title = f"{county_name} County — {slug.replace('-', ' ').title()}"
            (county_dir / f"{slug}.html").write_text(
                wrap_as_embed(section_html, section_figs, title),
                encoding="utf-8",
            )

    print(
        f"  Wrote 2 overview embeds + {len(order)} KPI embeds + "
        f"{len(order) * len(SECTION_BUILDERS)} chart embeds to {embeds_dir}"
    )


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Loading QCEW data...")
    raw = fetch_all_data()
    if raw.empty:
        print("ERROR: No data available. Check your internet connection.")
        sys.exit(1)

    df = clean(raw)
    print(f"  {len(df):,} rows for {df['county_name'].nunique()} counties")

    # Guard the secondary KPI row. When a FRED key IS configured, an empty GDP
    # or unemployment fetch means a real failure (e.g. a 429 rate limit), not an
    # intentional keyless run — so abort BEFORE writing any files. The Action's
    # commit step is skipped on a failed build, leaving last week's good values
    # published instead of overwriting them with "(unavailable)". With no key
    # set (local/no-key runs), skip the guard and let the row degrade to "—".
    # The fetches cache on success, so build_html/write_embeds reuse these.
    from data.fetch_fred import (
        fred_key_configured, fetch_real_gdp, fetch_unemployment_rate,
    )
    if fred_key_configured():
        # Call both (so each caches on success) before deciding, and name the
        # offending series in the abort message for faster diagnosis.
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
                f"ERROR: FRED_API_KEY is set but the {' and '.join(empty)} "
                "fetch returned no data (likely rate-limited or a FRED outage). "
                "Aborting without writing so the currently published KPI values "
                "are preserved rather than blanked."
            )
            sys.exit(1)

    print("Building HTML dashboard...")
    html = build_html(df)

    DOCS_DIR.mkdir(exist_ok=True)
    output = DOCS_DIR / "index.html"
    output.write_text(html, encoding="utf-8")
    print(f"Done! {output} ({output.stat().st_size / 1024:.0f} KB)")

    print("Building embed pages...")
    write_embeds(df)
