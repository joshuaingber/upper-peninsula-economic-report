"""
Top counties by employment — the five largest UP counties (by latest total
covered employment), each shown with its year-over-year employment growth,
business (establishment) growth, and wage growth. Grouped bars mirror the way
the BLS QCEW data viewer summarizes county-level over-the-year change.
"""
from __future__ import annotations

import plotly.graph_objects as go
import pandas as pd

from data.clean import latest_county_summaries
from data.constants import NMU_GREEN, NMU_GOLD, NMU_STONE, NMU_GRAY
from utils.narratives import source_citation, format_industry_list


TOP_N = 5

METHODOLOGY_NOTE = (
    "The five UP counties with the most covered employment in the latest "
    "published quarter. Each county shows its over-the-year percent change in "
    "employment, establishment count (business growth), and average weekly wage, "
    "per BLS QCEW. Counties with suppressed totals are excluded from the ranking."
)

_METRICS = [
    ("oty_emp_pct", "Employment growth", NMU_GREEN),
    ("oty_estab_pct", "Business growth", NMU_GOLD),
    ("oty_wage_pct", "Wage growth", NMU_STONE),
]


def get_top_counties(df: pd.DataFrame, n: int = TOP_N) -> pd.DataFrame:
    """Latest-quarter summaries for the `n` counties with the most employment.

    Suppressed counties are dropped before ranking. Returns the
    latest_county_summaries columns, sorted by employment descending.
    """
    summary = latest_county_summaries(df)
    if summary.empty:
        return summary
    ranked = summary[~summary["is_suppressed"] & summary["employment"].notna()]
    return ranked.sort_values("employment", ascending=False).head(n).reset_index(drop=True)


def build_figure(top: pd.DataFrame) -> go.Figure:
    """Grouped bar chart: one group per county, one bar per OTY growth metric."""
    counties = top["county_name"] + " County"

    fig = go.Figure()
    for col, label, color in _METRICS:
        fig.add_trace(go.Bar(
            x=counties,
            y=top[col],
            name=label,
            marker_color=color,
            hovertemplate="%{x}<br>" + label + ": %{y:+.1f}% YoY<extra></extra>",
        ))

    fig.add_hline(y=0, line_color="black", line_width=1)

    fig.update_layout(
        barmode="group",
        bargap=0.25,
        bargroupgap=0.08,
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=460,
        margin=dict(t=30, b=80, l=70, r=20),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="top", y=-0.18, x=0),
        xaxis=dict(
            showgrid=False,
            showline=True, linecolor="black", linewidth=2, mirror=False,
            ticks="outside", tickcolor="black", ticklen=4,
        ),
        yaxis=dict(
            title="Year-over-year change",
            ticksuffix="%",
            showgrid=True, gridcolor=NMU_GRAY,
            zeroline=False,
            showline=True, linecolor="black", linewidth=2, mirror=False,
            ticks="outside", tickcolor="black", ticklen=4,
        ),
    )
    return fig


def render(df: pd.DataFrame):
    """Render the top-5-counties over-the-year growth comparison."""
    import streamlit as st

    st.markdown("### Largest County Economies")

    top = get_top_counties(df)
    if top.empty:
        st.info("No disclosable county totals available to rank.")
        return

    year, qtr = int(top["year"].iloc[0]), int(top["qtr"].iloc[0])
    names = top["county_name"].tolist()
    st.markdown(
        f"The Upper Peninsula's largest county economies by employment in "
        f"{year} Q{qtr} are {format_industry_list(names)}. The bars compare each "
        f"county's year-over-year growth in jobs, businesses, and wages."
    )

    fig = build_figure(top)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(source_citation("BLS QCEW", "https://www.bls.gov/cew/", "Quarterly"))
    st.caption(f"_{METHODOLOGY_NOTE}_")
