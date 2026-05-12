"""
Employment and salary trend lines — quarterly raw + STL trend overlay.
"""
from __future__ import annotations

import plotly.graph_objects as go
import pandas as pd

from data.analysis import deseasonalize_trend, project_trend, periods_to_current_quarter
from data.clean import get_total_covered
from data.constants import COUNTY_COLORS, FAU_BLUE, FAU_SKY_BLUE
from utils.formatting import fmt_currency
from utils.narratives import narrate_employment_trends, source_citation

METHODOLOGY_NOTE = (
    "Chart shows the STL trend (raw quarterly values omitted for clarity). "
    "Trend computed via STL decomposition (period=4, robust); salary on log scale. "
    "Projection extrapolates a linear fit through the last 4 trend points to the "
    "current calendar quarter — the horizon shrinks as new QCEW data is published. "
    "BLS does not publish seasonally adjusted QCEW — this is a custom estimate."
)


def _trend_input(totals: pd.DataFrame, col: str) -> pd.Series:
    """Series for STL: drop suppressed/incomplete tail rows, index by date."""
    clean = totals[~totals.get("is_suppressed", False).fillna(False)]
    clean = clean[clean["qtrly_estabs"].notna()]
    return clean.set_index("date")[col].sort_index()


def _build_chart(
    totals: pd.DataFrame,
    y_col: str,
    title: str,
    color: str,
    tickformat: str,
    hover_prefix: str,
    log_transform: bool,
) -> go.Figure:
    indexed = totals.set_index("date").sort_index()
    labels = indexed["year_qtr"]
    trend = deseasonalize_trend(_trend_input(totals, y_col), log_transform=log_transform)
    trend = trend.reindex(indexed.index)

    # Linear projection from the last 4 trend points, extended to the current
    # calendar quarter (shrinks as new QCEW data is published).
    trend_observed = trend.dropna()
    periods = (
        periods_to_current_quarter(trend_observed.index[-1])
        if not trend_observed.empty else 0
    )
    projection = project_trend(trend, periods=periods, lookback=4, log_transform=log_transform)

    hovertemplate = (
        "%{customdata}<br>%{fullData.name}: " + hover_prefix + "%{y:,.0f}<extra></extra>"
    )

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=trend.index,
            y=trend.values,
            customdata=labels.values,
            mode="lines",
            name="Trend",
            line=dict(color=color, width=3),
            hovertemplate=hovertemplate,
        )
    )
    if not projection.empty:
        last_trend_x = trend.dropna().index[-1]
        last_trend_y = trend.dropna().iloc[-1]
        proj_x = [last_trend_x] + list(projection.index)
        proj_y = [last_trend_y] + list(projection.values)
        proj_labels = ["Latest trend"] + [
            f"{d.year} Q{ {2:1, 5:2, 8:3, 11:4}[d.month] } (projected)"
            for d in projection.index
        ]
        fig.add_trace(
            go.Scatter(
                x=proj_x, y=proj_y,
                customdata=proj_labels,
                mode="lines+markers",
                name="Projected",
                line=dict(color=color, dash="dot", width=2.5),
                marker=dict(size=7, color=color, symbol="circle-open", line=dict(width=2, color=color)),
                hovertemplate=hovertemplate,
            )
        )
        # Faint projection-zone band.
        fig.add_vrect(
            x0=last_trend_x, x1=projection.index[-1],
            fillcolor=FAU_SKY_BLUE, opacity=0.5,
            layer="below", line_width=0,
            annotation_text="PROJECTED", annotation_position="top right",
            annotation_font=dict(size=9, color=color),
        )
    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        plot_bgcolor="white",
        paper_bgcolor="white",
        hovermode="x unified",
        height=420,
        margin=dict(t=50, b=80, l=60, r=20),
        legend=dict(orientation="h", yanchor="top", y=-0.18, x=0),
        xaxis=dict(
            showgrid=False, title="Quarter",
            showline=True, linecolor="black", linewidth=2, mirror=False,
            ticks="outside", tickcolor="black", ticklen=4,
        ),
        yaxis=dict(
            showgrid=False, tickformat=tickformat, title=title,
            showline=True, linecolor="black", linewidth=2, mirror=False,
            ticks="outside", tickcolor="black", ticklen=4,
        ),
    )
    return fig


def render(df: pd.DataFrame):
    """Render quarterly employment and salary trend charts for a single county."""
    import streamlit as st

    st.header("Employment & Salary Trends")

    totals = get_total_covered(df).sort_values("date")

    if totals.empty:
        st.info("No trend data available.")
        return

    county_name = str(totals["county_name"].iloc[0])
    earliest, latest = totals.iloc[0], totals.iloc[-1]

    empl_text = narrate_employment_trends(
        county_name=county_name,
        start_year=int(earliest["year"]),
        end_year=int(latest["year"]),
        start_empl=earliest["employment"],
        end_empl=latest["employment"],
    )

    start_wage = earliest["avg_annual_wage"]
    end_wage = latest["avg_annual_wage"]
    if pd.notna(start_wage) and pd.notna(end_wage) and start_wage > 0:
        wage_change = (end_wage - start_wage) / start_wage * 100
        direction = "rising" if wage_change >= 0 else "falling"
        wage_text = (
            f" Average annual wages went from {fmt_currency(start_wage)} to "
            f"{fmt_currency(end_wage)}, {direction} {abs(wage_change):.1f}% "
            f"over the same period."
        )
    else:
        wage_text = ""

    # Escape `$` so Streamlit's markdown doesn't parse "$58,240 to $76,180"
    # as a LaTeX math span.
    st.markdown((empl_text + wage_text).replace("$", "\\$"))

    color = COUNTY_COLORS.get(county_name, FAU_BLUE)

    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(
            _build_chart(
                totals,
                y_col="employment",
                title="Total Employment",
                color=color,
                tickformat=",.0f",
                hover_prefix="",
                log_transform=False,
            ),
            use_container_width=True,
        )
    with col2:
        st.plotly_chart(
            _build_chart(
                totals,
                y_col="avg_annual_wage",
                title="Average Salary",
                color=color,
                tickformat="$,.0f",
                hover_prefix="$",
                log_transform=True,
            ),
            use_container_width=True,
        )

    st.caption(source_citation("BLS QCEW", "https://www.bls.gov/cew/", "Quarterly"))
    st.caption(f"_{METHODOLOGY_NOTE}_")
