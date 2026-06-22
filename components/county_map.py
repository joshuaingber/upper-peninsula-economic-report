"""
Upper Peninsula county map — a choropleth of the 15 UP counties shaded by
year-over-year employment growth, with a hover summary of each county's latest
QCEW statistics (employment, establishments, average salary, each with its OTY
percent change). Counties with suppressed/missing data render uncolored and
hover as "N/A".

Geography is the standard plotly county GeoJSON keyed on 5-digit FIPS, filtered
to the UP so the map frames the peninsula tightly.
"""
from __future__ import annotations

import json
from pathlib import Path

import plotly.graph_objects as go
import pandas as pd
import requests

from data.clean import latest_county_summaries
from data.constants import COUNTIES, MAP_DIVERGING_SCALE, PLOTLY_FONT
from utils.formatting import fmt_number, fmt_currency
from utils.narratives import source_citation


METHODOLOGY_NOTE = (
    "Counties are shaded by the year-over-year change in total covered "
    "employment (latest published quarter vs. the same quarter one year prior), "
    "per BLS QCEW. Hover a county for its employment, establishment count, and "
    "average salary, each with its over-the-year change. Counties whose data BLS "
    "suppresses for confidentiality appear uncolored."
)

_GEOJSON_URL = (
    "https://raw.githubusercontent.com/plotly/datasets/master/"
    "geojson-counties-fips.json"
)
_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
_GEOJSON_CACHE = _CACHE_DIR / "us_counties.geojson"

_geojson_memo: dict | None = None


def _load_geojson() -> dict | None:
    """Load the US-counties GeoJSON, filtered to the UP, with disk + memo cache.

    Returns None if the GeoJSON can't be obtained (no network, no cache), in
    which case the map degrades to an informational message.
    """
    global _geojson_memo
    if _geojson_memo is not None:
        return _geojson_memo

    raw = None
    if _GEOJSON_CACHE.exists():
        try:
            raw = json.loads(_GEOJSON_CACHE.read_text())
        except Exception:
            raw = None
    if raw is None:
        try:
            resp = requests.get(_GEOJSON_URL, timeout=30)
            resp.raise_for_status()
            raw = resp.json()
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _GEOJSON_CACHE.write_text(json.dumps(raw))
        except Exception:
            return None

    # Keep only UP county features so fitbounds frames the peninsula.
    up_features = [f for f in raw.get("features", []) if f.get("id") in COUNTIES]
    _geojson_memo = {"type": "FeatureCollection", "features": up_features}
    return _geojson_memo


def _fmt_signed_pct(val) -> str:
    """'+3.2%' / '−1.1%' / 'N/A' (true minus sign, matches the KPI cards)."""
    if val is None or pd.isna(val):
        return "N/A"
    sign = "+" if val >= 0 else "−"
    return f"{sign}{abs(val):.1f}%"


def build_figure(summary: pd.DataFrame, geojson: dict) -> go.Figure:
    """Choropleth of UP counties shaded by OTY employment growth.

    `summary` is the output of latest_county_summaries(); `geojson` is the
    UP-filtered FeatureCollection from _load_geojson().
    """
    # Pre-format every hover field in Python so suppressed/NaN cells read "N/A"
    # rather than rendering a broken number via the hovertemplate.
    customdata = [
        [
            f"{r['county_name']} County",
            "N/A" if r["is_suppressed"] else fmt_number(r["employment"]),
            _fmt_signed_pct(None if r["is_suppressed"] else r["oty_emp_pct"]),
            "N/A" if r["is_suppressed"] else fmt_number(r["qtrly_estabs"]),
            _fmt_signed_pct(None if r["is_suppressed"] else r["oty_estab_pct"]),
            "N/A" if r["is_suppressed"] else fmt_currency(r["avg_annual_wage"]),
            _fmt_signed_pct(None if r["is_suppressed"] else r["oty_wage_pct"]),
        ]
        for _, r in summary.iterrows()
    ]

    # Color by OTY employment growth; suppressed counties get NaN → uncolored.
    z = [
        None if r["is_suppressed"] else r["oty_emp_pct"]
        for _, r in summary.iterrows()
    ]

    fig = go.Figure(go.Choropleth(
        geojson=geojson,
        featureidkey="id",
        locations=summary["area_fips"],
        z=z,
        zmid=0,
        colorscale=MAP_DIVERGING_SCALE,
        marker_line_color="white",
        marker_line_width=1,
        customdata=customdata,
        colorbar=dict(
            title=dict(text="Employment<br>growth (YoY)", side="right"),
            ticksuffix="%",
            thickness=14,
            len=0.7,
        ),
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Employment: %{customdata[1]} (%{customdata[2]} YoY)<br>"
            "Establishments: %{customdata[3]} (%{customdata[4]} YoY)<br>"
            "Average salary: %{customdata[5]} (%{customdata[6]} YoY)"
            "<extra></extra>"
        ),
    ))

    fig.update_geos(
        fitbounds="locations",
        visible=False,
        bgcolor="white",
        showlakes=True,
        lakecolor="white",
    )
    fig.update_layout(
        height=520,
        margin=dict(t=10, b=10, l=10, r=10),
        paper_bgcolor="white",
        geo=dict(bgcolor="white"),
        dragmode=False,
        font=dict(family=PLOTLY_FONT),
    )
    return fig


def render(df: pd.DataFrame):
    """Render the interactive UP county map with a QCEW hover summary."""
    import streamlit as st

    st.markdown("### Upper Peninsula at a Glance")

    summary = latest_county_summaries(df)
    geojson = _load_geojson()

    if summary.empty or geojson is None:
        st.info("County map unavailable — no county data or map geometry could be loaded.")
        return

    # Label the snapshot with the newest quarter present across counties.
    latest_row = summary.sort_values(["year", "qtr"]).iloc[-1]
    year, qtr = int(latest_row["year"]), int(latest_row["qtr"])

    disclosable = summary[~summary["is_suppressed"]]
    if not disclosable.empty:
        leader = disclosable.sort_values("oty_emp_pct", ascending=False).iloc[0]
        st.markdown(
            f"Across the Upper Peninsula's {len(summary)} counties in {year} Q{qtr}, "
            f"{leader['county_name']} County posted the strongest year-over-year "
            f"employment growth at {_fmt_signed_pct(leader['oty_emp_pct'])}. "
            f"Hover any county for its full QCEW snapshot."
        )

    fig = build_figure(summary, geojson)
    st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": False})
    st.caption(source_citation("BLS QCEW", "https://www.bls.gov/cew/", "Quarterly"))
    st.caption(f"_{METHODOLOGY_NOTE}_")
