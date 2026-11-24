

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

    # Year-over-year changes use a matched sample. BLS suppresses some
    # county-industry cells, and a county that is published in one year but
    # suppressed in the other would otherwise show up as regional growth or
    # decline (e.g. Marquette health care entering disclosure in 2026 Q1).
    # For each UP group and quarter, sum the current and prior-year values only
    # over counties published (not suppressed, non-missing) in both quarters.
    # Levels above remain the sum of all published counties.
    aggregate_df = _add_matched_yoy(df, aggregate_df, group_cols, trend_cols)

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


def _add_matched_yoy(df, aggregate_df, group_cols, trend_cols):
    """Attach matched-sample oty_* change columns to the UP aggregate.

    Prior-year values come from merging each county row with the same county,
    group, and quarter one year earlier (not a positional shift, so gaps in
    the quarter sequence cannot misalign years). A county contributes to a
    measure's change only when that measure is published in both quarters.
    Average weekly wage change is computed from matched total wages over
    matched average employment in each year.
    """
    emp_cols = ["month1_emplvl", "month2_emplvl", "month3_emplvl"]
    base_measures = [m for m in trend_cols if m != "avg_wkly_wage"]
    cols = ["county_name", *group_cols, *base_measures]

    county = df[cols].copy()
    published = ~df["is_suppressed"].fillna(False).astype(bool)
    for m in base_measures:
        county[m] = county[m].where(published)

    prior = county.copy()
    prior["year"] = prior["year"] + 1
    paired = county.merge(
        prior, on=["county_name", *group_cols], how="inner",
        suffixes=("", "_prior"), validate="one_to_one",
    )

    sums = {}
    for m in base_measures:
        both = paired[m].notna() & paired[f"{m}_prior"].notna()
        sums[f"{m}__cur"] = paired[m].where(both)
        sums[f"{m}__prior"] = paired[f"{m}_prior"].where(both)

    # Wage: wages and all three monthly employment figures in both years.
    wage_cols = ["total_qtrly_wages", *emp_cols]
    both = paired[wage_cols].notna().all(axis=1) & paired[
        [f"{c}_prior" for c in wage_cols]
    ].notna().all(axis=1)
    sums["wages__cur"] = paired["total_qtrly_wages"].where(both)
    sums["wages__prior"] = paired["total_qtrly_wages_prior"].where(both)
    sums["avgemp__cur"] = paired[emp_cols].mean(axis=1).where(both)
    sums["avgemp__prior"] = paired[[f"{c}_prior" for c in emp_cols]].mean(axis=1).where(both)

    matched = pd.concat([paired[group_cols], pd.DataFrame(sums)], axis=1)
    matched = matched.groupby(group_cols, as_index=False, dropna=False).sum(min_count=1)

    for m in base_measures:
        matched[f"{m}__chg"] = matched[f"{m}__cur"] - matched[f"{m}__prior"]
        matched[f"{m}__pct"] = (
            matched[f"{m}__chg"] / matched[f"{m}__prior"].replace(0, float("nan")) * 100
        )
    wage_cur = matched["wages__cur"] / (matched["avgemp__cur"] * 13).replace(0, float("nan"))
    wage_prior = matched["wages__prior"] / (matched["avgemp__prior"] * 13).replace(0, float("nan"))
    matched["avg_wkly_wage__chg"] = wage_cur - wage_prior
    matched["avg_wkly_wage__pct"] = (
        matched["avg_wkly_wage__chg"] / wage_prior.replace(0, float("nan")) * 100
    )

    keep = {}
    for m, (change_col, pct_col) in trend_cols.items():
        keep[f"{m}__chg"] = change_col
        keep[f"{m}__pct"] = pct_col
    matched = matched[[*group_cols, *keep]].rename(columns=keep)

    aggregate_df = aggregate_df.drop(
        columns=[c for c in keep.values() if c in aggregate_df.columns]
    )
    return aggregate_df.merge(matched, on=group_cols, how="left")
