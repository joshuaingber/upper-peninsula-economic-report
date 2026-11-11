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

from data.clean import latest_benchmark, latest_county_summaries
from data.constants import (
    AGGLVL_STATE_TOTAL, AGGLVL_US_TOTAL, COUNTIES, MAP_DIVERGING_SCALE,
    NMU_DARK_GRAY, NMU_STONE, PLOTLY_FONT,
)
from utils.formatting import fmt_number, fmt_currency
from utils.narratives import source_citation


METHODOLOGY_NOTE = (
    "Counties are shaded by the year-over-year change in total covered "
    "employment (latest published quarter vs. the same quarter one year prior), "
    "per BLS QCEW. Hover a county for its employment, establishment count, and "
    "average salary, each with its over-the-year change. Counties whose data BLS "
    "suppresses for confidentiality appear uncolored. The small stone-colored U.S. and "
    "Michigan maps give national and statewide totals for comparison."
)

# Benchmark insets: display name -> (hover title, state codes drawn, label under inset)
BENCHMARK_LABELS = {
    "United States": "United States",
    "Michigan": "Michigan (statewide)",
}
_US_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE",
    "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD",
    "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
]

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


def _hover_row(title: str, r, suppressed: bool = False) -> list[str]:
    """Pre-formatted hover fields so missing/suppressed cells read "N/A"."""
    def get(k):
        return None if suppressed else r.get(k)
    return [
        title,
        fmt_number(get("employment")),
        _fmt_signed_pct(get("oty_emp_pct")),
        fmt_number(get("qtrly_estabs")),
        _fmt_signed_pct(get("oty_estab_pct")),
        fmt_currency(get("avg_annual_wage")),
        _fmt_signed_pct(get("oty_wage_pct")),
    ]


_HOVER = (
    "<b>%{customdata[0]}</b><br>"
    "Employment: %{customdata[1]} (%{customdata[2]} YoY)<br>"
    "Establishments: %{customdata[3]} (%{customdata[4]} YoY)<br>"
    "Average salary: %{customdata[5]} (%{customdata[6]} YoY)"
    "<extra></extra>"
)


def load_benchmarks(summary: pd.DataFrame) -> dict | None:
    """U.S. and Michigan totals for the same quarter as the county snapshot.

    Returns {"United States": {...}, "Michigan": {...}} (field names as in
    latest_county_summaries), or None if there is no county snapshot.
    """
    from data.fetch import fetch_national_data, fetch_state_data

    if summary is None or summary.empty:
        return None
    latest = summary.sort_values(["year", "qtr"]).iloc[-1]
    year, qtr = int(latest["year"]), int(latest["qtr"])
    return {
        "United States": latest_benchmark(fetch_national_data(), AGGLVL_US_TOTAL, year, qtr),
        "Michigan": latest_benchmark(fetch_state_data(), AGGLVL_STATE_TOTAL, year, qtr),
    }


def _add_benchmark_insets(fig: go.Figure, benchmarks: dict) -> None:
    """Two small NMU Stone maps (U.S., Michigan) in the main map's white space.

    A single NMU brand neutral (NMU_STONE, ~3.5:1 on white, clears the 3:1
    non-text minimum) keeps them visibly separate from the red-gold-green growth scale; a text label names each one,
    and the same values are in the map's data table (WCAG 1.1.1 / 1.4.1).
    """
    # (name, locations, geo id, domain x, domain y, label x, label y, label anchor)
    insets = [
        ("United States", _US_STATES, "geo2", [0.0, 0.2], [0.05, 0.29], 0.03, 0.04, "left"),
        ("Michigan", ["MI"], "geo3", [0.66, 0.84], [0.05, 0.32], 0.75, 0.04, "center"),
    ]
    for name, locs, geo_id, dx, dy, lx, ly, anchor in insets:
        row = _hover_row(BENCHMARK_LABELS[name], benchmarks.get(name) or {})
        fig.add_trace(go.Choropleth(
            locationmode="USA-states",
            locations=locs,
            z=[1] * len(locs),
            colorscale=[[0, NMU_STONE], [1, NMU_STONE]],
            showscale=False,
            marker_line_color="white",
            marker_line_width=0.4,
            customdata=[row] * len(locs),
            hovertemplate=_HOVER,
            geo=geo_id,
            name=BENCHMARK_LABELS[name],
        ))
        geo = dict(
            domain=dict(x=dx, y=dy), visible=False, bgcolor="rgba(0,0,0,0)",
            showlakes=True, lakecolor="white", projection_type="albers usa",
        )
        if name == "Michigan":
            geo.update(scope="usa", fitbounds="locations")
        else:
            geo.update(scope="usa")
        fig.update_layout(**{geo_id: geo})
        fig.add_annotation(
            text=name,
            x=lx, y=ly, xref="paper", yref="paper", xanchor=anchor, yanchor="top",
            showarrow=False, font=dict(size=12, color=NMU_DARK_GRAY),
        )


def build_figure(summary: pd.DataFrame, geojson: dict, benchmarks: dict | None = None) -> go.Figure:
    """Choropleth of UP counties shaded by OTY employment growth.

    `summary` is the output of latest_county_summaries(); `geojson` is the
    UP-filtered FeatureCollection from _load_geojson(). If `benchmarks` (from
    load_benchmarks) is given, small U.S. and Michigan maps are added whose
    hovers show national and statewide totals.
    """
    customdata = [
        _hover_row(f"{r['county_name']} County", r, bool(r["is_suppressed"]))
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
        # Black county boundaries, not white: on the diverging red->gold->green
        # scale the near-zero counties render light gold, and white 1px borders
        # vanish against them (~1.6:1). Black clears the light-gold midtone with
        # room to spare (~13:1) and is the best single-color worst-case across the
        # whole scale. A single border can't hit 3:1 against both the light middle
        # and the dark red/green ends, so this is a best-effort separation cue;
        # the map's data table remains the normative fallback (WCAG 1.1.1).
        marker_line_color="black",
        marker_line_width=1.5,
        customdata=customdata,
        colorbar=dict(
            title=dict(text="Employment<br>growth (YoY)", side="right"),
            ticksuffix="%",
            thickness=14,
            len=0.7,
        ),
        hovertemplate=_HOVER,
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
        geo=dict(bgcolor="white", domain=dict(x=[0, 1], y=[0, 1])),
        dragmode=False,
        font=dict(family=PLOTLY_FONT),
    )
    if benchmarks:
        _add_benchmark_insets(fig, benchmarks)
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

    fig = build_figure(summary, geojson, load_benchmarks(summary))
    st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": False})
    st.caption(source_citation("BLS QCEW", "https://www.bls.gov/cew/", "Quarterly"))
    st.caption(f"_{METHODOLOGY_NOTE}_")
