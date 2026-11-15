import pandas as pd


def get_county_risk_data(
    mit_ai_risk_merged_df: pd.DataFrame,
    selected_county: str,
) -> pd.DataFrame:
    county_data = mit_ai_risk_merged_df.loc[
        mit_ai_risk_merged_df["county_name"] == selected_county
    ].dropna(subset=["risk_score", "number_of_workers", "weighted_score"])
    return county_data.loc[county_data["number_of_workers"] > 0].copy()


def build_figure(
    county_data: pd.DataFrame,
    selected_county: str,
    weighted_average: float,
):
    import plotly.graph_objects as go

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=county_data["risk_score"],
        y=county_data["number_of_workers"],
        histfunc="sum",
        xbins={"start": 0.5, "end": 5.5, "size": 1},
        name="Workers by sector vulnerability score",
        marker_color="#1D4ED8",
        opacity=0.85,
        hovertemplate="Risk score: %{x}<br>Workers: %{y:,.0f}<extra></extra>",
    ))
    fig.add_vline(
        x=weighted_average,
        line_color="#B42318",
        line_width=3,
        line_dash="dash",
        annotation_text=f"Employment-weighted average: {weighted_average:.2f}",
        annotation_position="top right",
    )

    fig.update_layout(
        title=f"{selected_county} County AI Vulnerability by Sector",
        xaxis_title="AI vulnerability score (1 = low, 5 = high)",
        yaxis_title="Workers represented",
        xaxis={"tickmode": "array", "tickvals": [1, 2, 3, 4, 5]},
        bargap=0.2,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Arial"),
        height=500,
        margin=dict(t=50, b=50, l=50, r=50),
    )
    return fig


def render_county_ai_risk_score_hist(
    mit_ai_risk_merged_df: pd.DataFrame,
    selected_county: str,
) -> None:
    import streamlit as st

    county_data = get_county_risk_data(mit_ai_risk_merged_df, selected_county)

    if county_data.empty:
        st.info(f"No AI vulnerability rating data is available for {selected_county} County.")
        return

    total_workers = county_data["number_of_workers"].sum()
    weighted_average = county_data["weighted_score"].sum() / total_workers

    fig = build_figure(county_data, selected_county, weighted_average)

    st.markdown(
        f"Employment-weighted average vulnerability score: **{weighted_average:.2f} / 5** "
        f"across **{total_workers:,.0f} workers** in "
        f"**{len(county_data)} rated sectors**."
    )
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("**Data behind the chart**")
    st.dataframe(
        county_data[
            ["target_code", "risk_score", "number_of_workers", "weighted_score"]
        ]
        .rename(
            columns={
                "target_code": "Sector",
                "risk_score": "Vulnerability score",
                "number_of_workers": "Workers",
                "weighted_score": "Weighted score contribution",
            }
        )
        .sort_values("Sector")
        .reset_index(drop=True),
        hide_index=True,
        use_container_width=True,
    )