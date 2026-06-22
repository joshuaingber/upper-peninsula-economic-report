"""
Firm Openings & Closings — quarterly establishment churn aggregated from
industry-level QoQ deltas. Industries adding establishments stack above zero;
industries losing establishments stack below; the sum equals the county's net
QoQ change in establishment count. A dashed gold line overlays the U.S. national
rate rescaled to the county's establishment base for like-for-like comparison.
"""
from __future__ import annotations

import plotly.graph_objects as go
import pandas as pd

from data.clean import get_firm_formation_data, get_national_qoq_pct
from data.constants import (
    FAU_BLUE, FAU_RED, FAU_DARK_GRAY, FAU_SAND, AGGLVL_TOTAL_BY_OWN,
    PLOTLY_FONT,
)
from data.fetch import fetch_national_data
from utils.narratives import source_citation


METHODOLOGY_NOTE = (
    "Each blue bar sums the QoQ establishment growth across industries that "
    "gained firms; the red bar sums the loss across industries that shed firms. "
    "The dark line shows the county's BLS-published private establishment net "
    "change (own_code=5, agglvl=71) — it does not equal the sum of the bars "
    "because BLS suppresses small-cell industries from the per-sector view. The "
    "dashed gold benchmark is U.S. private-sector QoQ growth rescaled to the "
    "county's private establishment base — like-for-like with the bars. "
    "Trailing quarters with no benchmark mean the national figure hasn't been "
    "published yet. Q1 typically shows a large negative pattern across counties "
    "due to year-end reporting cycles in QCEW. This is not true gross firm "
    "openings and closings — BLS does not publish those at the county level."
)


def build_figure(
    plot_data: pd.DataFrame,
    national_pct: pd.Series | None = None,
    county_prev_estabs: pd.Series | None = None,
) -> go.Figure:
    """Quarterly establishment additions/losses bars with national benchmark overlay."""
    x = plot_data["year_qtr"]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x, y=plot_data["additions"],
        name="Industries adding establishments",
        marker_color=FAU_BLUE,
        hovertemplate="%{x}<br>Adding: +%{y:,.0f} establishments<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=x, y=plot_data["subtractions"],
        name="Industries losing establishments",
        marker_color=FAU_RED,
        hovertemplate="%{x}<br>Losing: %{y:,.0f} establishments<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=x, y=plot_data["net"],
        mode="lines+markers",
        name="County net (BLS-published, private)",
        line=dict(color=FAU_DARK_GRAY, width=2),
        marker=dict(size=5, color=FAU_DARK_GRAY,
                    line=dict(width=1, color="white")),
        hovertemplate="%{x}<br>County net: %{y:+,.0f} establishments<extra></extra>",
    ))

    # Optional national benchmark trace: U.S. QoQ pct rescaled to county scale.
    if national_pct is not None and county_prev_estabs is not None and not national_pct.empty:
        nat_pct_aligned = national_pct.reindex(plot_data["date"].values)
        prev_estabs_aligned = county_prev_estabs.reindex(plot_data["date"].values)
        benchmark = (nat_pct_aligned * prev_estabs_aligned).values
        if pd.notna(benchmark).any():
            fig.add_trace(go.Scatter(
                x=x, y=benchmark,
                mode="lines+markers",
                name="U.S. avg rate (rescaled)",
                line=dict(color=FAU_SAND, dash="dash", width=2),
                marker=dict(size=5, color=FAU_SAND),
                customdata=nat_pct_aligned.values,
                hovertemplate=(
                    "%{x}<br>U.S. avg rate: %{customdata:+.2%}"
                    "<br>At county scale: %{y:+,.0f} establishments<extra></extra>"
                ),
                connectgaps=False,
            ))

    fig.add_hline(y=0, line_color="black", line_width=1)

    fig.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family=PLOTLY_FONT),
        height=460,
        margin=dict(t=40, b=210, l=70, r=20),
        barmode="relative",
        legend=dict(orientation="h", yanchor="top", y=-0.55, x=0),
        hovermode="x unified",
        xaxis=dict(
            title=dict(text="Quarter", standoff=20),
            automargin=True,
            showgrid=False,
            showline=True, linecolor="black", linewidth=2, mirror=False,
            ticks="outside", tickcolor="black", ticklen=4,
            tickangle=-45,
        ),
        yaxis=dict(
            title="Quarterly change in establishments",
            showgrid=False,
            showline=True, linecolor="black", linewidth=2, mirror=False,
            ticks="outside", tickcolor="black", ticklen=4,
            tickformat="+,.0f",
            zeroline=False,
        ),
    )
    return fig


def _load_national_benchmark(df: pd.DataFrame):
    """Returns (national_pct, county_prev_estabs) on a private-only basis.

    Both sides are own_code=5 (private) so the benchmark line is apples-to-
    apples with the industry bars. Falls back to (None, None) on any failure.
    """
    try:
        national_pct = get_national_qoq_pct(fetch_national_data(), own_code=5)
        if national_pct.empty:
            return None, None
        # County-private total: own_code=5, agglvl=71 (single row per quarter)
        county_private = df[
            (df["own_code"] == 5) & (df["agglvl_code"] == AGGLVL_TOTAL_BY_OWN)
        ]
        if county_private.empty:
            return None, None
        county_estabs = (
            county_private.set_index("date")["qtrly_estabs"].sort_index()
        )
        county_prev_estabs = county_estabs.shift(1)
        return national_pct, county_prev_estabs
    except Exception:
        return None, None


def render(df: pd.DataFrame):
    """Quarterly establishment churn with U.S. national benchmark overlay."""
    import streamlit as st

    st.header("Firm Openings & Closings")

    plot_data = get_firm_formation_data(df)
    if plot_data.empty:
        st.info("Not enough establishment data to compute quarterly churn.")
        return

    national_pct, county_prev_estabs = _load_national_benchmark(df)

    latest = plot_data.iloc[-1]
    direction = "expanded" if latest["net"] > 0 else ("contracted" if latest["net"] < 0 else "held flat")
    parts = [
        f"In the most recent quarter ({latest['year_qtr']}), the county's "
        f"establishment count {direction} by {abs(int(latest['net'])):,} firms — "
        f"the net of {int(latest['additions']):,} added across growing industries "
        f"and {int(abs(latest['subtractions'])):,} lost across shrinking ones."
    ]
    st.markdown("".join(parts))

    fig = build_figure(plot_data, national_pct, county_prev_estabs)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(source_citation("BLS QCEW", "https://www.bls.gov/cew/", "Quarterly"))
    st.caption(f"_{METHODOLOGY_NOTE}_")
    if national_pct is None:
        st.caption("_(National benchmark unavailable for this run.)_")
