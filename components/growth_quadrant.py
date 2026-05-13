"""
Industry Landscape — YoY employment growth × YoY wage growth.
Bubbles colored by industry domain (FAU palette); each of the four quadrants
carries a faint FAU-palette tint, à la Amber's Industry Landscape mockup.
Identification is hover-only; no on-bubble labels.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import pandas as pd

from data.clean import get_growth_quadrant_data
from data.constants import (
    INDUSTRY_DOMAIN_COLORS, FAU_DARK_GRAY, FAU_GRAY, FAU_STONE, FAU_SKY_BLUE,
)
from utils.narratives import source_citation, format_industry_list


METHODOLOGY_NOTE = (
    "Growth rates compare each industry's employment and average wage in the "
    "latest quarter to the same quarter one year ago, per BLS QCEW."
)


def _axis_range(s: pd.Series, target_pad_frac: float = 0.15) -> list[float]:
    """Range that always includes zero and pads either symmetrically or one-sided."""
    if s.min() >= 0:
        return [-0.15 * s.max(), s.max() * 1.15]
    if s.max() <= 0:
        return [s.min() * 1.15, -0.15 * abs(s.min())]
    pad = max(2.0, target_pad_frac * max(abs(s.min()), abs(s.max())))
    return [s.min() - pad, s.max() + pad]


def build_figure(plot_data: pd.DataFrame) -> go.Figure:
    """Year-over-year employment vs. wage growth quadrant scatter, bubble-sized by employment."""
    x = plot_data["oty_month3_emplvl_pct_chg"]
    y = plot_data["oty_avg_wkly_wage_pct_chg"]
    x_range = _axis_range(x)
    y_range = _axis_range(y)

    sizes = np.sqrt(plot_data["employment"])
    bubble_colors = (
        plot_data["industry_label"].map(INDUSTRY_DOMAIN_COLORS).fillna(FAU_STONE)
    )

    fig = go.Figure()

    # Quadrant background tints (FAU palette, all four quadrants) — drawn first
    # so bubbles render on top.
    quadrant_tints = [
        # x0, x1, y0, y1, fillcolor
        (0, x_range[1], 0, y_range[1], FAU_SKY_BLUE),                       # NE
        (x_range[0], 0, 0, y_range[1], "rgba(212, 185, 139, 0.15)"),        # NW: FAU_SAND
        (x_range[0], 0, y_range[0], 0, "rgba(204, 0, 0, 0.08)"),            # SW: FAU_RED
        (0, x_range[1], y_range[0], 0, "rgba(122, 151, 171, 0.12)"),        # SE: FAU_STONE
    ]
    for x0, x1, y0, y1, fc in quadrant_tints:
        fig.add_shape(
            type="rect", layer="below",
            x0=x0, x1=x1, y0=y0, y1=y1,
            fillcolor=fc, line=dict(width=0),
        )

    # Bubbles — markers only, identification via hover.
    fig.add_trace(go.Scatter(
        x=x, y=y,
        mode="markers",
        marker=dict(
            size=sizes,
            sizemode="area",
            sizeref=2.0 * sizes.max() / (50 ** 2),
            sizemin=8,
            color=bubble_colors,
            line=dict(width=1, color="white"),
        ),
        customdata=plot_data[["industry_label", "oty_month3_emplvl_pct_chg",
                              "oty_avg_wkly_wage_pct_chg", "employment"]].values,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Employment growth (YoY): %{customdata[1]:+.1f}%<br>"
            "Wage growth (YoY): %{customdata[2]:+.1f}%<br>"
            "Employment: %{customdata[3]:,.0f}<extra></extra>"
        ),
        showlegend=False,
    ))

    # Dashed zero divider lines.
    fig.add_vline(x=0, line_dash="dash", line_color=FAU_GRAY, line_width=1)
    fig.add_hline(y=0, line_dash="dash", line_color=FAU_GRAY, line_width=1)

    # CAPS quadrant labels in paper-coordinate corners — always shown.
    corner_labels = [
        (0.98, 0.98, "right", "top",    "GROWING JOBS + WAGES"),
        (0.02, 0.98, "left",  "top",    "WAGES UP, JOBS SHRINKING"),
        (0.02, 0.02, "left",  "bottom", "DECLINING ON BOTH"),
        (0.98, 0.02, "right", "bottom", "JOBS UP, WAGES DOWN"),
    ]
    for x_p, y_p, xa, ya, txt in corner_labels:
        fig.add_annotation(
            x=x_p, y=y_p, xref="paper", yref="paper",
            text=txt, showarrow=False,
            xanchor=xa, yanchor=ya,
            font=dict(size=9, color=FAU_DARK_GRAY,
                      family="Source Sans Pro, sans-serif"),
        )

    fig.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=550,
        margin=dict(t=30, b=70, l=80, r=30),
        xaxis=dict(
            title="Employment Growth Rate (year over year) →",
            ticksuffix="%",
            zeroline=False,
            showgrid=False,
            range=x_range,
        ),
        yaxis=dict(
            title="Wage Growth Rate (year over year) ↑",
            ticksuffix="%",
            zeroline=False,
            showgrid=False,
            range=y_range,
        ),
    )
    return fig


def render(df: pd.DataFrame):
    """Quadrant scatter: industries placed by YoY employment vs salary growth."""
    import streamlit as st

    st.header("Industry Landscape")

    plot_data = get_growth_quadrant_data(df)
    if plot_data.empty:
        st.info("No disclosable industry growth data for this quarter.")
        return

    year, qtr = int(plot_data["year"].iloc[0]), int(plot_data["qtr"].iloc[0])

    ne = plot_data[(plot_data["oty_month3_emplvl_pct_chg"] > 0) & (plot_data["oty_avg_wkly_wage_pct_chg"] > 0)]
    sw = plot_data[(plot_data["oty_month3_emplvl_pct_chg"] < 0) & (plot_data["oty_avg_wkly_wage_pct_chg"] < 0)]

    parts = [
        f"Each bubble is a 2-digit NAICS industry in {year} Q{qtr}; size reflects "
        f"total employment. The horizontal split at 0% salary growth and the vertical "
        f"split at 0% employment growth define four regions. Both growth "
        f"rates are year over year."
    ]
    if not ne.empty:
        names = ne.nlargest(3, "employment")["industry_label"].tolist()
        parts.append(
            f" Industries expanding on both fronts (jobs and pay): {format_industry_list(names)}."
        )
    if not sw.empty:
        names = sw.nlargest(2, "employment")["industry_label"].tolist()
        parts.append(f" {format_industry_list(names)} are losing both jobs and pay growth.")

    st.markdown("".join(parts))

    fig = build_figure(plot_data)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(source_citation("BLS QCEW", "https://www.bls.gov/cew/", "Quarterly"))
    st.caption(f"_{METHODOLOGY_NOTE}_")
