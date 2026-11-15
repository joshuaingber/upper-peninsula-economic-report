"""
A time series spanning [t1] to [t2] years of the median house value per year for every county
in the UP.

## Future upgrades ##
Add trend line prediction like in employment_trends.py if possible
"""
from __future__ import annotations

import plotly.graph_objects as go
import pandas as pd
from data.constants import COUNTY_COLORS, FAU_BLUE, FAU_SKY_BLUE, PLOTLY_FONT
from utils.narratives import narrate_median_house_value_trends, source_citation

METHODOLOGY_NOTE = (
    "Chart shows the median home value per year for the selected Upper Peninsula "
    "county. Years with no Census estimate are omitted from the chart. Data comes "
    "from the U.S. Census Bureau's American Community Survey (ACS) 5-year estimates."
)

# t-series graph
# Builds the median home value time-series figure for one county's rows.
def build_figure(df: pd.DataFrame) -> go.Figure:
    """Sorts df by year, draws one line trace in the county's color, and
    applies the same white-background, ruled-axis layout as the trends charts.

    df must hold a single county's rows with `year`, `median_home_value`, and
    `county_name` columns. Years are plotted as whole numbers (ACS 5-year
    estimates are annual), and the hover shows the dollar value.
    """
    rows = df.sort_values("year")
    county_name = str(rows["county_name"].iloc[0])
    color = COUNTY_COLORS.get(county_name, FAU_BLUE)
    title = "Median Home Value"

    fig = go.Figure([go.Scatter(
        x=rows["year"],
        y=rows["median_home_value"],
        mode="lines+markers",
        line=dict(color=color, width=3),
        marker=dict(size=6, color=color),
        name=title,
        hovertemplate="%{x}<br>" + title + ": $%{y:,.0f}<extra></extra>",
    )])
    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        font=dict(family=PLOTLY_FONT),
        plot_bgcolor="white", paper_bgcolor="white",
        hovermode="x unified", height=440,
        margin=dict(t=50, b=60, l=100, r=20),
        showlegend=False,
        xaxis=dict(
            showgrid=False, dtick=1, tickformat="d",
            title=dict(text="Year", standoff=15),
            showline=True, linecolor="black", linewidth=2, mirror=False,
            ticks="outside", tickcolor="black", ticklen=4,
        ),
        yaxis=dict(
            showgrid=False, tickformat="$,.0f",
            title=dict(text=title, standoff=15),
            showline=True, linecolor="black", linewidth=2, mirror=False,
            ticks="outside", tickcolor="black", ticklen=4,
        ),
    )
    return fig


# Renders the median home value time series for one county in Streamlit.
def render(df: pd.DataFrame):
    """Shows the narrative, then the chart from build_figure, then the source
    and methodology captions.

    df is one county's housing rows. If it's empty, it shows a short info
    message instead.
    """
    import streamlit as st

    st.header("Median Home Value Trends")

    totals = df.sort_values("year")

    if totals.empty:
        st.info("No trend data available.")
        return

    county_name = str(totals["county_name"].iloc[0])
    earliest, latest = totals.iloc[0], totals.iloc[-1]

    med_house_value_text = narrate_median_house_value_trends(
        county_name=county_name,
        start_year=int(earliest["year"]),
        end_year=int(latest["year"]),
        start_value=earliest["median_home_value"],
        end_value=latest["median_home_value"],
    )

    # Escape `$` so Streamlit's markdown doesn't parse "$58,240 to $76,180"
    # as a LaTeX math span.
    st.markdown((med_house_value_text).replace("$", "\\$"))

    st.plotly_chart(build_figure(totals), use_container_width=True)

    st.caption(source_citation("U.S. Census Bureau ACS", "https://www.census.gov/programs-surveys/acs/", "Annual"))
    st.caption(f"_{METHODOLOGY_NOTE}_")



