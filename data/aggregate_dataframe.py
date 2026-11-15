

import pandas as pd
from data.clean import SUPERSECTOR_DOMAIN_CODES, SUPERSECTOR_LABELS, QUARTER_TO_MONTH



def get_aggregate_data(df: pd.DataFrame) -> pd.DataFrame:
    """Create an Upper Peninsula aggregate while preserving QCEW hierarchy.

    1. Remove previously created Aggregate rows and prepare industry codes.
    2. Group counties by ownership, industry, hierarchy, size, and quarter.
    3. Sum underlying employment, establishment, and wage measures.
    4. Recalculate derived employment and wage measures.
    5. Recalculate year-over-year changes within each hierarchy group.
    6. Rebuild dates, labels, and other fields normally created by clean().
    7. Set geography, suppression, and location quotient fields appropriately.
    8. Preserve original column order and append any additional columns.
    """
    if df.empty:
        return df

    df = df.copy()

    # Remove previously created Aggregate rows
    df = df[df["county_name"] != "Upper Peninsula"].copy()

    # Ensure industry codes remain strings (e.g., "10", "1021")
    df["industry_code"] = df["industry_code"].astype(str)

    # Columns defining distinct, non-overlapping QCEW groups
    group_cols = [
        "own_code",
        "industry_code",
        "agglvl_code",
        "size_code",
        "year",
        "qtr",
    ]

    # Measures that can be summed across counties
    sum_cols = [
        "qtrly_estabs",
        "month1_emplvl",
        "month2_emplvl",
        "month3_emplvl",
        "total_qtrly_wages",
        "taxable_qtrly_wages",
        "qtrly_contributions",
    ]

    # Sum underlying measures across counties
    aggregate_df = (
        df.groupby(group_cols, as_index=False, dropna=False)[sum_cols]
        .sum(min_count=1)
    )

    # Recalculate derived employment and wage measures
    aggregate_df["employment"] = aggregate_df["month3_emplvl"]

    avg_quarterly_employment = aggregate_df[
        ["month1_emplvl", "month2_emplvl", "month3_emplvl"]
    ].mean(axis=1)

    aggregate_df["avg_wkly_wage"] = (
        aggregate_df["total_qtrly_wages"]
        / (avg_quarterly_employment * 13).replace(0, float("nan"))
    )

    aggregate_df["avg_annual_wage"] = (
        aggregate_df["avg_wkly_wage"] * 52
    )

    # Recalculate year-over-year changes within each hierarchy group
    trend_cols = {
        "qtrly_estabs": (
            "oty_qtrly_estabs_chg",
            "oty_qtrly_estabs_pct_chg",
        ),
        "month1_emplvl": (
            "oty_month1_emplvl_chg",
            "oty_month1_emplvl_pct_chg",
        ),
        "month2_emplvl": (
            "oty_month2_emplvl_chg",
            "oty_month2_emplvl_pct_chg",
        ),
        "month3_emplvl": (
            "oty_month3_emplvl_chg",
            "oty_month3_emplvl_pct_chg",
        ),
        "total_qtrly_wages": (
            "oty_total_qtrly_wages_chg",
            "oty_total_qtrly_wages_pct_chg",
        ),
        "taxable_qtrly_wages": (
            "oty_taxable_qtrly_wages_chg",
            "oty_taxable_qtrly_wages_pct_chg",
        ),
        "qtrly_contributions": (
            "oty_qtrly_contributions_chg",
            "oty_qtrly_contributions_pct_chg",
        ),
        "avg_wkly_wage": (
            "oty_avg_wkly_wage_chg",
            "oty_avg_wkly_wage_pct_chg",
        ),
    }

    aggregate_df = aggregate_df.sort_values(
        ["own_code", "industry_code", "agglvl_code",
         "size_code", "year", "qtr"]
    ).reset_index(drop=True)

    trend_groups = [
        "own_code",
        "industry_code",
        "agglvl_code",
        "size_code",
    ]

    for measure, (change_col, pct_col) in trend_cols.items():
        prior_year = aggregate_df.groupby(trend_groups)[measure].shift(4)

        aggregate_df[change_col] = aggregate_df[measure] - prior_year

        aggregate_df[pct_col] = (
            aggregate_df[change_col]
            / prior_year.replace(0, float("nan"))
            * 100
        )

    # Rebuild fields normally created by clean()
    aggregate_df["year_qtr"] = (
        aggregate_df["year"].astype(int).astype(str)
        + " Q"
        + aggregate_df["qtr"].astype(int).astype(str)
    )

    aggregate_df["date"] = pd.to_datetime(
        aggregate_df["year"].astype(int).astype(str)
        + "-"
        + aggregate_df["qtr"].map(QUARTER_TO_MONTH).astype(str)
        + "-01"
    )

    # Rebuild industry labels
    aggregate_df["industry_code"] = (
        aggregate_df["industry_code"].astype("string").str.strip()
    )

    aggregate_df["industry_label"] = (
        aggregate_df["industry_code"].map(SUPERSECTOR_DOMAIN_CODES)
    )

    naics_mask = aggregate_df["industry_label"].isna()

    aggregate_df.loc[naics_mask, "industry_label"] = (
        aggregate_df.loc[naics_mask, "industry_code"]
        .map(SUPERSECTOR_LABELS)
    )

    aggregate_df["industry_label"] = (
        aggregate_df["industry_label"]
        .fillna(aggregate_df["industry_code"])
    )

    aggregate_df.loc[
        aggregate_df["industry_code"] == "10",
        "industry_label",
    ] = "Total, All Industries"

    # Set aggregate geography and disclosure fields
    aggregate_df["county_name"] = "Upper Peninsula"
    aggregate_df["area_fips"] = pd.NA

    for col in [
        "disclosure_code",
        "oty_disclosure_code",
        "lq_disclosure_code",
    ]:
        if col in df.columns:
            aggregate_df[col] = pd.NA

    # Do not sum or average county location quotients
    lq_cols = [
        col for col in aggregate_df.columns
        if col.startswith("lq_")
    ]

    aggregate_df[lq_cols] = float("nan")

    # Aggregate suppression cannot be determined from county flags alone
    aggregate_df["is_suppressed"] = False

    # Preserve original columns and append additional derived columns
    for col in df.columns:
        if col not in aggregate_df.columns:
            aggregate_df[col] = pd.NA

    original_cols = [
        col for col in df.columns
        if col in aggregate_df.columns
    ]

    extra_cols = [
        col for col in aggregate_df.columns
        if col not in original_cols
    ]

    aggregate_df = aggregate_df[original_cols + extra_cols]

    # Sort consistently with the county-level DataFrame
    aggregate_df = aggregate_df.sort_values(
        ["county_name", "date", "industry_code"]
    ).reset_index(drop=True)

    return aggregate_df
