#Create a industry wide summary bargraph for the upper peninsula industries
#using latest quarter data from the QCEW dataset. The bargraph will show the total covered employment for each industry in the upper peninsula, sorted in descending order. 
#The bargraph will also show the percent change in employment from the previous quarter and the previous year. 
#The bargraph will be interactive, allowing users to hover over each bar to see the exact values. 
#The bargraph will also have a title and a source citation.

import pandas as pd
import plotly.graph_objects as go

from data.constants import (
    AGGLVL_NAICS_SECTOR,
    AGGLVL_TOTAL_BY_OWN,
    INDUSTRY_DOMAIN_COLORS,
    PLOTLY_FONT,
    SUPERSECTOR_LABELS,
)

PRIVATE_OWN_CODE = 5  # QCEW ownership code for private employers


# Summarizes the largest private industries across the whole UP by employment, share, establishments, and pay.
def build_industry_summary(df: pd.DataFrame, year: int | None = None) -> pd.DataFrame:
    """Keeps private-ownership rows, then picks the latest year with all four
    quarters if year isn't given. Monthly employment is averaged into one
    figure per row. Sector rows (agglvl 74) are summed across counties within
    each quarter, then employment and establishments are averaged over the
    quarters while wages are summed over them. Average annual pay is total
    wages divided by average employment, which weights counties correctly.
    Share is sector employment over the private all-industries total
    (agglvl 71, industry_code 10), computed the same way. Returns one row per
    industry, largest first.
    """
    private = df[df["own_code"] == PRIVATE_OWN_CODE].copy()
    private["industry_code"] = private["industry_code"].astype(str)

    if year is None:
        quarters_per_year = private.groupby("year")["qtr"].nunique()
        year = quarters_per_year[quarters_per_year == 4].index.max()
    private = private[private["year"] == year]

    private["emplvl"] = private[
        ["month1_emplvl", "month2_emplvl", "month3_emplvl"]
    ].mean(axis=1)

    sectors = private[private["agglvl_code"] == AGGLVL_NAICS_SECTOR]
    total = private[
        (private["agglvl_code"] == AGGLVL_TOTAL_BY_OWN)
        & (private["industry_code"] == "10")
    ]

    by_quarter = sectors.groupby(["industry_code", "qtr"], as_index=False).agg(
        emplvl=("emplvl", "sum"),
        estabs=("qtrly_estabs", "sum"),
        wages=("total_qtrly_wages", "sum"),
    )
    summary = by_quarter.groupby("industry_code", as_index=False).agg(
        employment=("emplvl", "mean"),
        establishments=("estabs", "mean"),
        annual_wages=("wages", "sum"),
    )

    total_employment = total.groupby("qtr")["emplvl"].sum().mean()
    summary["share_of_private"] = summary["employment"] / total_employment
    summary["avg_annual_pay"] = summary["annual_wages"] / summary["employment"]
    summary["industry"] = summary["industry_code"].map(SUPERSECTOR_LABELS)
    summary["year"] = year

    summary = summary[summary["employment"] > 0].drop(columns="annual_wages")
    return summary.sort_values("employment", ascending=False).reset_index(drop=True)


# Draws a horizontal bar chart of the top private UP industries by employment, with share labeled on each bar.
def plot_industry_summary(summary: pd.DataFrame, top_n: int = 10) -> go.Figure:
    """Takes the top_n rows of the summary and reverses them so the largest bar
    sits at the top. Bar length is employment, bar color comes from
    INDUSTRY_DOMAIN_COLORS by industry name, the label on each bar is the
    share of private employment, and hovering shows establishments and
    average annual pay.
    """
    top = summary.head(top_n).iloc[::-1]
    colors = [INDUSTRY_DOMAIN_COLORS.get(name, "#7E8C84") for name in top["industry"]]

    fig = go.Figure(
        go.Bar(
            x=top["employment"],
            y=top["industry"],
            orientation="h",
            marker_color=colors,
            text=[f"{s:.1%}" for s in top["share_of_private"]],
            textposition="outside",
            customdata=top[["establishments", "avg_annual_pay"]],
            hovertemplate=(
                "<b>%{y}</b><br>Employment: %{x:,.0f}<br>"
                "Establishments: %{customdata[0]:,.0f}<br>"
                "Avg annual pay: $%{customdata[1]:,.0f}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title=f"Largest private industries in the Upper Peninsula, {int(top['year'].iloc[0])}",
        xaxis_title="Average employment",
        font_family=PLOTLY_FONT,
        margin=dict(l=10, r=40, t=60, b=40),
    )
    return fig