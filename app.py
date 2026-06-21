"""
Upper Peninsula Regional Economic Report
Built with Streamlit + Plotly using BLS QCEW data.
Covers the 15 counties of Michigan's Upper Peninsula.

Adapted from Bryan Cutsinger's South Florida Economic Report
(https://github.com/bryanpcutsinger/south-florida-economic-report, MIT).
"""
import streamlit as st
import pandas as pd

from data.fetch import fetch_all_data
from data.fetch_fred import fetch_real_gdp, fetch_unemployment_rate
from data.fetch_irs_migration import fetch_irs_migration
from data.clean import (
    clean, get_total_covered, get_latest_quarter,
    latest_gdp_with_growth, latest_unrate_with_yoy, latest_irs_net,
)
from data.constants import (
    FAU_BLUE, FAU_RED, FAU_DARK_GRAY, FAU_GRAY, FAU_ELECTRIC_BLUE,
    FAU_SKY_BLUE, COUNTY_COLORS, COUNTIES,
)
from utils.formatting import fmt_number, fmt_currency
from utils.narratives import source_citation

from components.county_map import render as render_county_map
from components.top_counties import render as render_top_counties
from components.employment_trends import render as render_trends
from components.growth_quadrant import render as render_growth_quadrant
from components.firm_formation import render as render_firm_formation
from components.employment_treemap import render as render_employment_treemap

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Upper Peninsula Regional Economic Report",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
)

# ── NMU Theme CSS ─────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
    /* White background throughout */
    .stApp {{
        background-color: #FFFFFF;
    }}
    section[data-testid="stSidebar"] {{
        background-color: #F8F9FA;
    }}

    /* Header styling */
    .main-title {{
        color: {FAU_BLUE};
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0;
        padding-bottom: 0;
    }}
    .main-subtitle {{
        color: {FAU_DARK_GRAY};
        font-size: 1.0rem;
        margin-top: 0;
    }}

    /* County snapshot cards */
    .county-card {{
        background: linear-gradient(135deg, #F8F9FA 0%, #FFFFFF 100%);
        border-radius: 12px;
        padding: 1.5rem;
        border-left: 5px solid;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        margin-bottom: 1rem;
    }}
    .county-card h3 {{
        margin: 0 0 0.8rem 0;
        font-size: 1.3rem;
    }}
    .kpi-row {{
        display: flex;
        justify-content: space-between;
        gap: 0.8rem;
    }}
    .kpi-item {{
        flex: 1;
        text-align: center;
    }}
    .kpi-label {{
        font-size: 0.75rem;
        color: {FAU_DARK_GRAY};
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 0.2rem;
        min-height: 1.8rem;
        line-height: 0.9rem;
    }}
    .kpi-value {{
        font-size: 1.4rem;
        font-weight: 700;
        color: {FAU_BLUE};
    }}
    .kpi-delta {{
        font-size: 0.8rem;
        margin-top: 0.1rem;
    }}
    .kpi-delta.positive {{
        color: #2E7D32;
    }}
    .kpi-delta.negative {{
        color: {FAU_RED};
    }}
    /* Secondary KPI row (real GDP, unemployment, net migration) — typography
       matches the primary row; only the separator distinguishes them. */
    .kpi-row.secondary {{
        margin-top: 0.9rem;
        padding-top: 0.7rem;
        border-top: 1px solid {FAU_GRAY};
    }}
    .kpi-period {{
        font-size: 0.7rem;
        color: #888;
        margin-top: 0.15rem;
    }}

    /* Data quarter badge */
    .data-badge {{
        display: inline-block;
        background-color: {FAU_SKY_BLUE};
        color: {FAU_BLUE};
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 500;
        margin-bottom: 1.5rem;
    }}

    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 0;
        border-bottom: 2px solid {FAU_GRAY};
    }}
    .stTabs [data-baseweb="tab"] {{
        padding: 0.75rem 1.5rem;
        font-weight: 500;
        color: {FAU_DARK_GRAY};
    }}
    .stTabs [aria-selected="true"] {{
        border-bottom: 3px solid {FAU_BLUE};
        color: {FAU_BLUE};
    }}

    /* Make all Streamlit text dark on white */
    .stMarkdown, .stMetric, .stCaption, p, span, label {{
        color: {FAU_DARK_GRAY};
    }}
    h1, h2, h3, h4, h5, h6 {{
        color: {FAU_BLUE} !important;
    }}

    /* Override Streamlit metric styling */
    [data-testid="stMetricValue"] {{
        color: {FAU_BLUE};
    }}
    [data-testid="stMetricLabel"] {{
        color: {FAU_DARK_GRAY};
    }}
</style>
""", unsafe_allow_html=True)

# ── Title ─────────────────────────────────────────────────────────────────────
st.markdown('<p class="main-title">Upper Peninsula Regional Economic Report</p>', unsafe_allow_html=True)
st.markdown('<p class="main-subtitle">Quarterly Census of Employment and Wages (QCEW) &mdash; the 15 counties of Michigan&rsquo;s Upper Peninsula</p>', unsafe_allow_html=True)

# ── Load and clean data ──────────────────────────────────────────────────────
raw_df = fetch_all_data()
if raw_df.empty:
    st.info("Fetching data from BLS... please refresh the page in a moment.")
    st.stop()

df = clean(raw_df)

# Secondary KPI data sources — fetched once at module load (cache-hot after the
# first run). Each loader returns an empty DataFrame on missing key/network
# failure so the secondary KPI cells degrade individually to "—".
_df_gdp_secondary = fetch_real_gdp()
_df_unrate_secondary = fetch_unemployment_rate()
_df_irs_secondary = fetch_irs_migration()


def _secondary_for(county_name: str) -> dict:
    return {
        "gdp": latest_gdp_with_growth(_df_gdp_secondary, county_name),
        "unrate": latest_unrate_with_yoy(_df_unrate_secondary, county_name),
        "irs": latest_irs_net(_df_irs_secondary, county_name),
    }


# ── Regional Snapshot ─────────────────────────────────────────────────────────

def _county_snapshot_card(county_df: pd.DataFrame, county_name: str, color: str,
                          secondary=None):
    """Render a styled KPI card for one county (primary + optional secondary row)."""
    totals = get_total_covered(county_df)
    latest = get_latest_quarter(totals)

    if latest.empty:
        st.markdown(f"""
        <div class="county-card" style="border-left-color: {color};">
            <h3 style="color: {color};">{county_name} County</h3>
            <p>No data available.</p>
        </div>
        """, unsafe_allow_html=True)
        return

    row = latest.iloc[0]
    year, qtr = int(row["year"]), int(row["qtr"])

    empl = fmt_number(row["employment"])
    estabs = fmt_number(row["qtrly_estabs"])
    wage = fmt_currency(row["avg_annual_wage"])

    empl_pct = row.get("oty_month3_emplvl_pct_chg")
    estab_pct = row.get("oty_qtrly_estabs_pct_chg")
    wage_pct = row.get("oty_avg_wkly_wage_pct_chg")

    def _delta_html(pct):
        if pd.isna(pct):
            return ""
        css_class = "positive" if pct >= 0 else "negative"
        arrow = "&#9650;" if pct >= 0 else "&#9660;"
        return f'<div class="kpi-delta {css_class}">{arrow} {abs(pct):.1f}% YoY</div>'

    secondary = secondary or {}
    secondary_html = _secondary_row_html(secondary)

    st.markdown(f"""
    <div class="county-card" style="border-left-color: {color};">
        <h3 style="color: {color};">{county_name} County</h3>
        <div class="kpi-row">
            <div class="kpi-item">
                <div class="kpi-label">Employment</div>
                <div class="kpi-value">{empl}</div>
                {_delta_html(empl_pct)}
            </div>
            <div class="kpi-item">
                <div class="kpi-label">Establishments</div>
                <div class="kpi-value">{estabs}</div>
                {_delta_html(estab_pct)}
            </div>
            <div class="kpi-item">
                <div class="kpi-label">Average Salary</div>
                <div class="kpi-value">{wage}</div>
                {_delta_html(wage_pct)}
            </div>
        </div>
        {secondary_html}
    </div>
    """, unsafe_allow_html=True)


def _secondary_row_html(secondary: dict) -> str:
    """Build the second KPI row HTML — GDP + Unemployment + Net Migration."""
    gdp = secondary.get("gdp") or {}
    unr = secondary.get("unrate") or {}
    irs = secondary.get("irs") or {}

    # GDP cell: level + YoY growth (positive = good)
    if gdp:
        gdp_value = f"${gdp['value_billions']:.1f}B"
        growth = gdp["yoy_growth"]
        gdp_arrow = "&#9650;" if growth >= 0 else "&#9660;"
        gdp_class = "positive" if growth >= 0 else "negative"
        gdp_delta = f'<div class="kpi-delta {gdp_class}">{gdp_arrow} {abs(growth)*100:.1f}% YoY</div>'
        gdp_period = f'<div class="kpi-period">({gdp["year"]})</div>'
    else:
        gdp_value, gdp_delta, gdp_period = "—", "", '<div class="kpi-period">(unavailable)</div>'

    # Unemployment cell: rate + YoY pp delta.
    # Arrow tracks the rate's direction (▲ rose, ▼ fell). Color is INVERTED
    # so rising = red (bad), falling = green (good) — lower-is-better.
    if unr:
        unr_value = f"{unr['rate']:.1f}%"
        delta = unr["yoy_delta_pp"]
        unr_arrow = "&#9650;" if delta >= 0 else "&#9660;"  # rate up = ▲, rate down = ▼
        unr_class = "negative" if delta >= 0 else "positive"  # up = red (bad), down = green (good)
        unr_delta = f'<div class="kpi-delta {unr_class}">{unr_arrow} {abs(delta):.1f}pp YoY</div>'
        unr_period = f'<div class="kpi-period">({unr["month_label"]})</div>'
    else:
        unr_value, unr_delta, unr_period = "—", "", '<div class="kpi-period">(unavailable)</div>'

    # Net migration cell: signed integer + two-year flow label
    # (NO arrow — sign IS the headline). Label calls out the two-year window
    # explicitly; underlying flow is IRS SOI "Total Migration-US and Foreign".
    if irs:
        sign = "+" if irs["net_exemptions"] >= 0 else "−"
        irs_value = f"{sign}{abs(irs['net_exemptions']):,}"
        irs_delta = ""  # no arrow on migration
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

# Show the data quarter badge
sample_totals = get_total_covered(df)
sample_latest = get_latest_quarter(sample_totals)
if not sample_latest.empty:
    sample_row = sample_latest.iloc[0]
    st.markdown(f'<div class="data-badge">Data as of {int(sample_row["year"])} Q{int(sample_row["qtr"])}</div>', unsafe_allow_html=True)

# ── Regional Snapshot: interactive map + largest-county comparison ────────────
render_county_map(df)

st.divider()

render_top_counties(df)

# ── County Detail (selectable) ────────────────────────────────────────────────

def _render_county_tab(county_df: pd.DataFrame, county_name: str):
    """Render the full QCEW analysis for a single county."""
    if county_df.empty:
        st.warning(f"No data available for {county_name} County.")
        return

    # Employment Trends
    render_trends(county_df)

    # Workforce Composition
    st.divider()
    render_employment_treemap(county_df)

    # Industry Landscape
    st.divider()
    render_growth_quadrant(county_df)

    # Firm Openings & Closings
    st.divider()
    render_firm_formation(county_df)


st.divider()

st.markdown("### County Detail")

# Fifteen counties don't fit a tab strip, so a selector drives the per-county
# deep dive. Counties are ordered geographically (west → east) via COUNTIES;
# default to Marquette, the UP's largest economy.
county_names = list(COUNTIES.values())
default_idx = county_names.index("Marquette") if "Marquette" in county_names else 0
selected_county = st.selectbox(
    "Select a county", county_names, index=default_idx,
    label_visibility="collapsed",
)

selected_df = df[df["county_name"] == selected_county]
selected_color = COUNTY_COLORS.get(selected_county, FAU_BLUE)
_county_snapshot_card(
    selected_df, selected_county, selected_color, _secondary_for(selected_county)
)
st.caption(
    "Net Migration reflects IRS SOI county-to-county filings (Total Migration-US "
    "and Foreign) — the net change in tax-filer exemptions between consecutive "
    "filing years, inclusive of moves into and out of the country. FRED real GDP "
    "and unemployment rate vintages reflect the most recent BEA/BLS releases as "
    "of the data badge above. Small UP counties may show '—' where BLS/BEA/IRS "
    "suppress or omit a series for confidentiality."
)

_render_county_tab(selected_df, selected_county)

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    source_citation("BLS QCEW", "https://www.bls.gov/cew/", "Quarterly")
)
