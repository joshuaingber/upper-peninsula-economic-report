"""
Workforce Composition — treemap of private employment by NAICS sector,
with year-selector buttons that switch the snapshot to the latest published
quarter of any year for which BLS QCEW data is available.

Implementation: one Plotly Treemap trace per year, all attached to the same
figure; only the newest trace is visible by default. Plotly's `updatemenus`
buttons toggle which trace is visible AND update the chart title to confirm
the active snapshot in plain text.
"""
from __future__ import annotations

import plotly.graph_objects as go
import pandas as pd

from data.clean import get_treemap_snapshots
from data.constants import (
    INDUSTRY_DOMAIN_COLORS, FAU_DARK_GRAY, FAU_GRAY, FAU_STONE, FAU_SAND,
    PLOTLY_FONT,
)
from utils.narratives import source_citation, format_industry_list


METHODOLOGY_NOTE = (
    "Each rectangle is a 2-digit NAICS sector; size is total private employment "
    "in the displayed quarter. Use the buttons below the chart to view earlier "
    "years; the narrative reflects the most recent quarter. Colors group "
    "sectors into broad industry domains (matching the Industry Landscape "
    "chart). Sectors with suppressed BLS data and 'Unclassified' are excluded."
)


def _text_color_for(domain_color: str) -> str:
    """Pick contrast text color: dark gray on FAU_SAND (light), white otherwise."""
    return FAU_DARK_GRAY if domain_color == FAU_SAND else "white"


def build_figure(snapshots: list) -> go.Figure:
    """Multi-trace treemap with year-selector updatemenus.

    `snapshots` is a list of (year, qtr, plot_data) tuples sorted ASCENDING
    by year. The LAST trace (newest year) starts visible; buttons render
    left-to-right with year-only labels (oldest on the left). The chart title
    above and the trace `name` retain the full "YYYY QQ" form for textual
    confirmation of the active snapshot.
    """
    fig = go.Figure()
    n = len(snapshots)
    default_idx = n - 1  # newest year is the last item in ascending order

    for idx, (year, qtr, plot_data) in enumerate(snapshots):
        domain_colors = [
            INDUSTRY_DOMAIN_COLORS.get(label, FAU_STONE)
            for label in plot_data["industry_label"]
        ]
        text_colors = [_text_color_for(c) for c in domain_colors]
        fig.add_trace(go.Treemap(
            labels=plot_data["industry_label"],
            parents=[""] * len(plot_data),
            values=plot_data["employment"],
            customdata=plot_data[["share", "qtrly_estabs", "avg_annual_wage"]].values,
            marker=dict(colors=domain_colors, line=dict(width=2, color="white")),
            textinfo="label+value",
            texttemplate="<b>%{label}</b><br>%{value:,.0f} (%{customdata[0]:.1%})",
            textfont=dict(
                family=PLOTLY_FONT,
                size=12,
                color=text_colors,
            ),
            hovertemplate=(
                "<b>%{label}</b><br>"
                "Employment: %{value:,.0f}<br>"
                "Establishments: %{customdata[1]:,.0f}<br>"
                "Average salary: $%{customdata[2]:,.0f}<br>"
                "Share of private workforce: %{customdata[0]:.1%}"
                "<extra></extra>"
            ),
            sort=True,
            visible=(idx == default_idx),
            name=f"{year} Q{qtr}",
        ))

    # Year-only button labels (e.g., "2019" .. "2025"). Buttons silently
    # toggle which trace is visible; the button row is the only active-snapshot
    # cue (no above-chart title).
    buttons = [
        dict(
            label=f"{year}",
            method="update",
            args=[{"visible": [i == idx for i in range(n)]}],
        )
        for idx, (year, qtr, _) in enumerate(snapshots)
    ]

    fig.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family=PLOTLY_FONT),
        height=560,
        margin=dict(t=30, b=70, l=10, r=10),
        updatemenus=[dict(
            type="buttons",
            direction="right",
            x=0.5, xanchor="center",
            y=-0.05, yanchor="top",
            pad=dict(t=8, b=4),
            bgcolor="white",
            bordercolor=FAU_GRAY,
            borderwidth=1,
            font=dict(color=FAU_DARK_GRAY, size=11),
            active=default_idx,
            buttons=buttons,
        )],
    )
    return fig


def render(df: pd.DataFrame):
    """Workforce Composition treemap with year-selector buttons."""
    import streamlit as st

    st.header("Workforce Composition")

    snapshots = get_treemap_snapshots(df)
    if not snapshots:
        st.info("No disclosable employment data for this quarter.")
        return

    # Narrative reflects the most recent (default-visible) snapshot.
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

    st.markdown(narrative)
    fig = build_figure(snapshots)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(source_citation("BLS QCEW", "https://www.bls.gov/cew/", "Quarterly"))
    st.caption(f"_{METHODOLOGY_NOTE}_")
