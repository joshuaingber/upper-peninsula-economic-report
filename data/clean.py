# QCEW cleaning and filtering: turns raw BLS data into analysis-ready tables,
# and derives the per-county KPI values shown on the regional snapshot card.
"""
Cleaning pipeline and filtering helpers for QCEW data.
Handles type conversion, derived fields, disclosure suppression, and industry labeling.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd

from data.constants import (
    NUMERIC_COLS,
    SUPERSECTOR_LABELS,
    SUPERSECTOR_DOMAIN_CODES,
    AGGLVL_TOTAL,
    AGGLVL_TOTAL_BY_OWN,
    AGGLVL_NAICS_SECTOR,
    AGGLVL_NAICS_4DIGIT,
    COUNTIES,
    TARGET_CODE_TO_NAICS
)


# Project-wide quarter-to-month convention: Q1→Feb, Q2→May, Q3→Aug, Q4→Nov.
# Mid-quarter dates so quarterly time-series points sit on the right calendar grid.
QUARTER_TO_MONTH = {1: 2, 2: 5, 3: 8, 4: 11}


# Adds a `date` column built from `year` and `qtr` using the mid-quarter
# convention. Returns a copy. Shared by clean() and get_national_qoq_pct() so
# the date convention has a single source of truth.
def add_date_column(df: pd.DataFrame) -> pd.DataFrame:
    """Copy df, then build a "YYYY-M-01" string per row and convert it to a datetime.

    The year comes from `year` (cast to int), and the month comes from mapping
    `qtr` through QUARTER_TO_MONTH. The result is appended as `date`.
    """
    df = df.copy()
    df["date"] = pd.to_datetime(
        df["year"].astype(int).astype(str) + "-"
        + df["qtr"].map(QUARTER_TO_MONTH).astype(str) + "-01"
    )
    return df


# Runs the full cleaning pipeline on raw county QCEW data: fixes types, adds
# derived fields (employment, dates, annual wage, suppression flag), and labels
# industries. Returns df unchanged if it is empty.
def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Copy df and apply these steps in order.

    1. Strip quote characters from the string code columns.
    2. Convert NUMERIC_COLS to numbers, turning unparseable values into NaN.
    3. Set is_suppressed to True where disclosure_code is "N".
    4. Set employment to month3_emplvl.
    5. Build year_qtr labels (e.g., "2024 Q2") and the date column.
    6. Set avg_annual_wage to avg_wkly_wage * 52.
    7. Sort by county_name, date, industry_code.
    8. Set industry_label from SUPERSECTOR_DOMAIN_CODES, then SUPERSECTOR_LABELS
       for codes that didn't match, then the raw industry_code for any still
       missing. Code "10" is always labeled "Total, All Industries".
    """
    if df.empty:
        return df

    df = df.copy()

    # Strip quotes from string columns (BLS CSVs are quote-wrapped)
    for col in ["area_fips", "industry_code", "disclosure_code",
                "lq_disclosure_code", "oty_disclosure_code"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip('" ')

    # Convert numeric columns — coerce errors to NaN (handles suppressed values)
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Mark disclosure-suppressed rows
    df["is_suppressed"] = df["disclosure_code"] == "N"

    # Employment: use third month of each quarter (most complete count)
    df["employment"] = df["month3_emplvl"]

    # Quarter/year label for charts (e.g., "2024 Q2")
    df["year_qtr"] = df["year"].astype(int).astype(str) + " Q" + df["qtr"].astype(int).astype(str)

    # Date column for time series (mid-quarter convention)
    df = add_date_column(df)

    # Derived: average annual wage (weekly × 52)
    df["avg_annual_wage"] = df["avg_wkly_wage"] * 52

    # Sort for consistent ordering
    df = df.sort_values(["county_name", "date", "industry_code"]).reset_index(drop=True)

    # Industry labels — merge supersector domain codes + NAICS sector labels
    df["industry_label"] = df["industry_code"].map(SUPERSECTOR_DOMAIN_CODES)
    naics_mask = df["industry_label"].isna()
    df.loc[naics_mask, "industry_label"] = df.loc[naics_mask, "industry_code"].map(SUPERSECTOR_LABELS)

    # Fallback: use industry_code itself if no label found
    still_missing = df["industry_label"].isna()
    df.loc[still_missing, "industry_label"] = df.loc[still_missing, "industry_code"]

    # Special label for totals
    df.loc[df["industry_code"] == "10", "industry_label"] = "Total, All Industries"

    return df


# ── Filtering helpers ─────────────────────────────────────────────────────────

# Returns the total covered employment rows (all ownerships combined).
def get_total_covered(df: pd.DataFrame) -> pd.DataFrame:
    """Keep rows where own_code is 0 and agglvl_code equals AGGLVL_TOTAL (70)."""
    return df[(df["own_code"] == 0) & (df["agglvl_code"] == AGGLVL_TOTAL)]


# Returns the 2-digit NAICS sector rows for one ownership type (private by default).
def get_naics_sectors(df: pd.DataFrame, own_code: int = 5) -> pd.DataFrame:
    """Keep rows matching own_code where agglvl_code equals AGGLVL_NAICS_SECTOR (74)."""
    return df[(df["own_code"] == own_code) & (df["agglvl_code"] == AGGLVL_NAICS_SECTOR)]


# Returns only the rows from the most recent quarter in the data.
def get_latest_quarter(df: pd.DataFrame) -> pd.DataFrame:
    """Find the maximum `date` and keep the rows equal to it; return df as is if empty."""
    if df.empty:
        return df
    max_date = df["date"].max()
    return df[df["date"] == max_date]


# Returns one row per county summarizing its latest-quarter total covered QCEW
# (employment, establishments, annual wage, and YoY changes). Counties with no
# total-covered data are omitted. Shared by the Upper Peninsula county map and
# the top-counties growth chart.
def latest_county_summaries(df: pd.DataFrame) -> pd.DataFrame:
    """Group get_total_covered(df) by county and take each county's latest quarter.

    Each county is reduced to the most recent quarter for which it has a
    total-covered row, and its first row from that quarter is used. Returns
    columns county_name, area_fips, year, qtr, employment, qtrly_estabs,
    avg_annual_wage, oty_emp_pct, oty_estab_pct, oty_wage_pct, and
    is_suppressed. The three oty_* values come from BLS's over-the-year
    percent-change columns and are None if a column is missing. Returns an
    empty DataFrame if there are no total-covered rows at all.
    """
    totals = get_total_covered(df)
    if totals.empty:
        return pd.DataFrame()

    rows = []
    for name, sub in totals.groupby("county_name"):
        latest = get_latest_quarter(sub)
        if latest.empty:
            continue
        r = latest.iloc[0]
        rows.append({
            "county_name": name,
            "area_fips": str(r.get("area_fips", "")),
            "year": int(r["year"]),
            "qtr": int(r["qtr"]),
            "employment": r["employment"],
            "qtrly_estabs": r["qtrly_estabs"],
            "avg_annual_wage": r["avg_annual_wage"],
            "oty_emp_pct": r.get("oty_month3_emplvl_pct_chg"),
            "oty_estab_pct": r.get("oty_qtrly_estabs_pct_chg"),
            "oty_wage_pct": r.get("oty_avg_wkly_wage_pct_chg"),
            "is_suppressed": bool(r.get("is_suppressed", False)),
        })
    return pd.DataFrame(rows)


def latest_benchmark(raw: pd.DataFrame, agglvl: int, year: int, qtr: int,
                     own_code: int = 0) -> dict:
    """One benchmark area's (U.S. or a state) total-covered QCEW for a given quarter.

    `raw` is an uncleaned national/state frame from data.fetch. The quarter is
    passed in so the benchmark matches the county snapshot instead of whatever
    is newest in the benchmark file. Returns the same field names as
    latest_county_summaries(); every value is None if that quarter is missing
    or BLS flagged it non-disclosable.
    """
    empty = {k: None for k in ("employment", "qtrly_estabs", "avg_annual_wage",
                               "oty_emp_pct", "oty_estab_pct", "oty_wage_pct")}
    if raw is None or raw.empty:
        return empty
    rows = raw[(raw["own_code"] == own_code) & (raw["agglvl_code"] == agglvl)
               & (raw["year"] == year) & (raw["qtr"] == qtr)]
    if rows.empty or str(rows.iloc[0].get("disclosure_code") or "").strip() == "N":
        return empty
    r = rows.iloc[0]
    return {
        "employment": r["month3_emplvl"],
        "qtrly_estabs": r["qtrly_estabs"],
        "avg_annual_wage": r["avg_wkly_wage"] * 52,
        "oty_emp_pct": r.get("oty_month3_emplvl_pct_chg"),
        "oty_estab_pct": r.get("oty_qtrly_estabs_pct_chg"),
        "oty_wage_pct": r.get("oty_avg_wkly_wage_pct_chg"),
    }


def get_growth_quadrant_data(df: pd.DataFrame) -> pd.DataFrame:
    """Take the latest quarter of get_naics_sectors(df, own_code=5) and filter it.

    Keeps rows that are not suppressed, are not labeled "Unclassified", have
    employment above zero, and have non-null oty_month3_emplvl_pct_chg and
    oty_avg_wkly_wage_pct_chg values. Returns a copy.
    """
    sectors = get_latest_quarter(get_naics_sectors(df, own_code=5))
    return sectors[
        (~sectors["is_suppressed"])
        & (sectors["industry_label"] != "Unclassified")
        & (sectors["employment"] > 0)
        & sectors["oty_month3_emplvl_pct_chg"].notna()
        & sectors["oty_avg_wkly_wage_pct_chg"].notna()
    ].copy()


# ── Secondary KPI derivation helpers ─────────────────────────────────────────
# Tiny pure functions consumed by the regional snapshot card to summarize
# the latest values of FRED + IRS series per county.


# Returns one county's latest annual real GDP (in billions) and its YoY growth
# rate. Returns {} when fewer than 2 observations exist (can't compute YoY).
def latest_gdp_with_growth(df_gdp: pd.DataFrame, county_name: str) -> dict:
    """Filter df_gdp to the county, sort by date, and compare the last two rows.

    value_billions is the latest value divided by 1,000,000 (FRED reports
    thousands of dollars). yoy_growth is (latest - prior) / prior as a
    fraction, so 0.03 means 3%. year is the latest observation's year.
    """
    if df_gdp.empty:
        return {}
    sub = df_gdp[df_gdp["county_name"] == county_name].sort_values("date")
    if len(sub) < 2:
        return {}
    latest = sub.iloc[-1]
    prior = sub.iloc[-2]
    return {
        "value_billions": float(latest["value"]) / 1_000_000,  # thousands → billions
        "yoy_growth": (float(latest["value"]) - float(prior["value"])) / float(prior["value"]),
        "year": int(latest["date"].year),
    }


# Returns one county's latest monthly unemployment rate and its change from the
# same month a year earlier, in percentage points. Returns {} if the
# prior-year month is missing, so the KPI cell falls back to "—".
def latest_unrate_with_yoy(df_unrate: pd.DataFrame, county_name: str) -> dict:
    """Take the county's last row, then find its same-month-one-year-prior row by date.

    The FRED LAUS series for these counties are NSA (not seasonally adjusted),
    so YoY uses a same-month-one-year-prior comparison. Matching is by
    month-precision date (to_period("M")) rather than positional indexing,
    so a gap in the monthly series — e.g., the Oct 2025 FRED outage caused
    by the BLS appropriations lapse — never silently shifts the comparison
    window. Returns rate, yoy_delta_pp, and month_label (formatted like
    "Mar 2026").
    """
    if df_unrate.empty:
        return {}
    sub = df_unrate[df_unrate["county_name"] == county_name].sort_values("date")
    if sub.empty:
        return {}
    latest = sub.iloc[-1]
    target_period = (latest["date"] - pd.DateOffset(years=1)).to_period("M")
    prior_matches = sub[sub["date"].dt.to_period("M") == target_period]
    if prior_matches.empty:
        return {}
    prior = prior_matches.iloc[0]
    return {
        "rate": float(latest["value"]),
        "yoy_delta_pp": float(latest["value"]) - float(prior["value"]),
        "month_label": latest["date"].strftime("%b %Y"),
    }


# Returns one county's most recent IRS net migration figure (US and foreign
# combined), along with both years of the migration window. Returns {} if the
# county has no row.
def latest_irs_net(df_irs: pd.DataFrame, county_name: str) -> dict:
    """Take the county's first row in df_irs and derive the two window years.

    dest_year is the row's tax_year, and origin_year is one year earlier, so
    the display can label the figure as a two-year flow rather than
    collapsing it to a single year. Returns net_exemptions, tax_year (retained
    for backward compatibility), origin_year, and dest_year.
    """
    if df_irs.empty:
        return {}
    sub = df_irs[df_irs["county_name"] == county_name]
    if sub.empty:
        return {}
    row = sub.iloc[0]
    dest_year = int(row["tax_year"])
    return {
        "net_exemptions": int(row["net_exemptions"]),
        "tax_year": dest_year,
        "origin_year": dest_year - 1,
        "dest_year": dest_year,
    }


# Returns one quarter's private-sector employment by NAICS sector, for the
# treemap. Uses the latest quarter available by default, or the latest quarter
# within a given year.
def get_employment_treemap_data(
    df: pd.DataFrame, year: Optional[int] = None
) -> pd.DataFrame:
    """Filter to disclosable private sectors, pick one quarter, and add each sector's share.

    Keeps own_code=5 rows that are not suppressed, not "Unclassified", and
    have employment above zero. With year=None it keeps the latest quarter
    overall; with year=YYYY it keeps the latest quarter within that year and
    returns an empty DataFrame if that year has no rows. share is each
    sector's employment divided by the sum across the remaining sectors, so
    shares add up to 1 over disclosable sectors, not over the whole county.
    Returns industry_label, employment, qtrly_estabs, avg_annual_wage, share,
    year, and qtr, sorted by employment descending.
    """
    sectors = get_naics_sectors(df, own_code=5)
    sectors = sectors[
        (~sectors["is_suppressed"])
        & (sectors["industry_label"] != "Unclassified")
        & (sectors["employment"] > 0)
    ].copy()
    if sectors.empty:
        return sectors

    if year is None:
        sectors = get_latest_quarter(sectors)
    else:
        sub = sectors[sectors["year"] == int(year)]
        if sub.empty:
            return sub.head(0)
        max_q = int(sub["qtr"].max())
        sectors = sub[sub["qtr"] == max_q]

    if sectors.empty:
        return sectors

    sectors = sectors.copy()
    total = sectors["employment"].sum()
    sectors["share"] = sectors["employment"] / total
    return (
        sectors[[
            "industry_label", "employment", "qtrly_estabs", "avg_annual_wage",
            "share", "year", "qtr",
        ]]
        .sort_values("employment", ascending=False)
        .reset_index(drop=True)
    )


# Returns a list of (year, latest_quarter) pairs, oldest first, for every year
# that has disclosable private-sector data.
def get_employment_treemap_years(df: pd.DataFrame) -> list[tuple[int, int]]:
    """Apply the treemap's sector filters, then take the maximum qtr within each year."""
    sectors = get_naics_sectors(df, own_code=5)
    sectors = sectors[
        (~sectors["is_suppressed"])
        & (sectors["industry_label"] != "Unclassified")
        & (sectors["employment"] > 0)
    ]
    if sectors.empty:
        return []
    yq = sectors.groupby("year")["qtr"].max().sort_index().reset_index()
    return [(int(r["year"]), int(r["qtr"])) for _, r in yq.iterrows()]


# Returns every (year, latest_quarter, treemap DataFrame) snapshot, oldest
# first. Callers that want only the most recent snapshot use snapshots[-1].
def get_treemap_snapshots(df: pd.DataFrame) -> list:
    """Loop over get_employment_treemap_years and build each year's treemap data.

    Returns a list of (int, int, pd.DataFrame) tuples. Years whose snapshot is
    empty (e.g., universally suppressed) are dropped so the caller never has
    to render a button with no underlying data.
    """
    years_asc = get_employment_treemap_years(df)
    snapshots = []
    for year, qtr in years_asc:
        snap = get_employment_treemap_data(df, year=year)
        if not snap.empty:
            snapshots.append((year, qtr, snap))
    return snapshots

# Returns one annual-average private-sector industry snapshot per complete
# year, summed across every county in df, as (year, plot_data) tuples oldest
# first. This is the UP-wide counterpart to get_treemap_snapshots, which
# assumes a single county's rows.
def get_up_industry_snapshots(df: pd.DataFrame) -> list:
    """Apply these steps in order.

    1. Take the private NAICS sector rows from get_naics_sectors(df, own_code=5)
       and drop rows that are suppressed or labeled "Unclassified", the same
       exclusions the treemap uses.
    2. Average each row's three monthly employment levels into emplvl. This is
       not the `employment` column, which is only the quarter's third month.
       Rows with emplvl of zero or less are dropped.
    3. Keep only complete years: the private all-industries total (agglvl 71)
       must have a row for every county in COUNTIES in all four quarters, so a
       year with a failed BLS request never shows partial sums.
    4. For each complete year, sum emplvl, qtrly_estabs, and total_qtrly_wages
       by industry across counties and quarters. Employment and establishments
       are divided by 4 to give annual averages. avg_annual_wage is total
       wages divided by average employment, so large counties weigh more than
       small ones.
    5. Set share to each industry's average employment over the private
       all-industries average employment (agglvl 71), falling back to the sum
       of the sectors if that total is missing.

    Returns a list of (int, pd.DataFrame) tuples with columns industry_label,
    employment, share, qtrly_estabs, and avg_annual_wage, each sorted by
    employment descending. Years with an empty snapshot are dropped.
    """
    sectors = get_naics_sectors(df, own_code=5).copy()
    sectors["emplvl"] = sectors[
        ["month1_emplvl", "month2_emplvl", "month3_emplvl"]
    ].mean(axis=1)
    sectors = sectors[
        (~sectors["is_suppressed"])
        & (sectors["industry_label"] != "Unclassified")
        & (sectors["emplvl"] > 0)
    ]

    totals = df[
        (df["own_code"] == 5) & (df["agglvl_code"] == AGGLVL_TOTAL_BY_OWN)
    ].copy()
    totals["emplvl"] = totals[
        ["month1_emplvl", "month2_emplvl", "month3_emplvl"]
    ].mean(axis=1)

    # A year is complete when every county has a total row in all four quarters
    county_quarters = (
        totals.drop_duplicates(["year", "county_name", "qtr"]).groupby("year").size()
    )
    complete_years = county_quarters[county_quarters == len(COUNTIES) * 4].index

    snapshots = []
    for year in sorted(complete_years):
        annual = (
            sectors[sectors["year"] == year]
            .groupby("industry_label", as_index=False)
            .agg(
                employment=("emplvl", "sum"),
                qtrly_estabs=("qtrly_estabs", "sum"),
                wages=("total_qtrly_wages", "sum"),
            )
        )
        if annual.empty:
            continue

        annual["employment"] = annual["employment"] / 4
        annual["qtrly_estabs"] = annual["qtrly_estabs"] / 4
        annual["avg_annual_wage"] = annual["wages"] / annual["employment"]

        # Private all-industries average employment; fall back to the sector sum
        total_employment = totals.loc[totals["year"] == year, "emplvl"].sum() / 4
        annual["share"] = annual["employment"] / (
            total_employment or annual["employment"].sum()
        )

        plot_data = (
            annual[["industry_label", "employment", "share", "qtrly_estabs", "avg_annual_wage"]]
            .sort_values("employment", ascending=False)
            .reset_index(drop=True)
        )
        snapshots.append((int(year), plot_data))

    return snapshots

# Returns the U.S. quarter-over-quarter percent change in establishment count
# for one ownership type, as a date-indexed Series. It is the national
# benchmark for the county firm-formation chart.
def get_national_qoq_pct(df_national: pd.DataFrame, own_code: int = 5) -> pd.Series:
    """Filter the raw national data to own_code, then take the pct change of qtrly_estabs.

    Defaults to private (own_code=5) so the firm-formation benchmark is
    apples-to-apples with the county's private-only industry data. Pass
    own_code=0 to get the all-ownership total covered series. Input is
    expected to contain both ownership slices per fetch_national_data's
    expanded filter — older caches without the requested slice return an
    empty Series and downstream consumers degrade gracefully. Otherwise it
    adds the date column, sorts by date, indexes by date, and drops the first
    quarter (which has no prior to compare with).
    """
    if df_national.empty or "qtrly_estabs" not in df_national.columns:
        return pd.Series(dtype=float)
    df = df_national[df_national["own_code"] == own_code]
    if df.empty:
        return pd.Series(dtype=float)
    df = add_date_column(df).sort_values("date").set_index("date")
    return df["qtrly_estabs"].pct_change().dropna()


# Returns, for each quarter, how many establishments were added across
# industries, how many were lost, and the county's net change. This is the
# data behind the firm-formation chart. It is the county-private establishment
# change with an industry-level breakdown, not gross firm openings and
# closings (BLS doesn't publish those at the county level).
def get_firm_formation_data(df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-industry quarterly changes, sum them into bars, and join the true net.

    For each (industry, quarter), compute the QoQ change in `qtrly_estabs`
    at (own_code=5, agglvl=74). Then aggregate per quarter:
      - additions    = sum of positive industry-level deltas (which industries added firms)
      - subtractions = sum of negative industry-level deltas (which industries lost firms; ≤ 0)
      - net          = BLS-published QoQ change in the county-private establishment count,
                       pulled from (own_code=5, agglvl=71).

    `net` does NOT equal `additions + subtractions` because BLS suppresses
    small-cell industries from the per-sector view at agglvl=74; agglvl=71
    is a single unsuppressed row per quarter. The visible gap between the
    stacked bars and the net line is the suppression effect.

    Suppressed, "Unclassified", and null-estabs sectors are excluded before
    the deltas are computed. The bars are merged with net on date, and the
    first quarter in the input series is dropped (no QoQ change available).
    Returns a DataFrame with a default integer index, sorted by date, with
    columns date, year_qtr, additions, subtractions, and net.
    """
    sectors = get_naics_sectors(df, own_code=5)
    sectors = sectors[
        (~sectors["is_suppressed"])
        & (sectors["industry_label"] != "Unclassified")
        & sectors["qtrly_estabs"].notna()
    ].copy()
    if sectors.empty:
        return pd.DataFrame(columns=["date", "year_qtr", "additions", "subtractions", "net"])

    sectors = sectors.sort_values(["industry_label", "date"])
    sectors["estabs_delta"] = sectors.groupby("industry_label")["qtrly_estabs"].diff()
    sectors = sectors.dropna(subset=["estabs_delta"])

    bars = (
        sectors.groupby(["date", "year_qtr"], as_index=False)
        .agg(
            additions=("estabs_delta", lambda s: s[s > 0].sum()),
            subtractions=("estabs_delta", lambda s: s[s < 0].sum()),
        )
    )

    # True county-private net from (own_code=5, agglvl=71) — single row per
    # quarter, no industry-level suppression.
    county_private = df[
        (df["own_code"] == 5) & (df["agglvl_code"] == AGGLVL_TOTAL_BY_OWN)
    ].sort_values("date").set_index("date")
    net_true = county_private["qtrly_estabs"].diff().rename("net")

    return (
        bars.merge(net_true, left_on="date", right_index=True, how="left")
        .sort_values("date")
        .reset_index(drop=True)
    )


## WORK IN PROGRESS ##

# loads the up_housing.parquet into a pd.Dataframe and drops row for a county if data is missing.
# Returns a df with features: housing_units, occupied_units, vacant_units, Owner_occupied, renter_occupied
#, median_home_value, median_gross_rent, year, fips, and county name.
# Df will then be used to support housing_data embeds
def clean_housing_data(df: pd.DataFrame) -> pd.Dataframe:
    for i in range(len(df)):
        for j in range(df.columns.size()):
            if df[i,j] == None:
                df.drop(i)
                print(f"Dropped row: ", i)
                break

    return(df)

# Keeps sector vulnerability ratings and averages the median score for each
# target code. The resulting scores are joined to county employment below.
def clean_mit_ai_safety_sector_rating(df: pd.DataFrame) -> pd.DataFrame:
    ratings = df[
        (df["target_type"] == "sector")
        & (df["criterion"] == "vulnerability")
    ]
    return (
        ratings.groupby("target_code", as_index=False)
        .agg(risk_score=("median", "mean"))
    )

# Aggregates latest-quarter QCEW employment into the MIT rating categories.
def clean_qcew_data_for_AI_risk_embed(df: pd.DataFrame) -> pd.DataFrame:
    result_columns = ["county_name", "target_code", "number_of_workers"]
    if df.empty:
        return pd.DataFrame(columns=result_columns)

    required_columns = {
        "county_name",
        "year",
        "qtr",
        "agglvl_code",
        "industry_code",
        "month3_emplvl",
    }
    missing_columns = required_columns.difference(df.columns)
    if missing_columns:
        raise ValueError(
            "QCEW data is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    quarter_keys = df[["year", "qtr"]].apply(pd.to_numeric, errors="coerce")
    valid_quarters = quarter_keys.dropna().sort_values(["year", "qtr"])
    if valid_quarters.empty:
        raise ValueError("QCEW data has no valid year/quarter values")
    latest = valid_quarters.iloc[-1]
    latest_mask = quarter_keys["year"].eq(latest["year"]) & quarter_keys["qtr"].eq(
        latest["qtr"]
    )
    latest_df = df.loc[latest_mask].copy()
    latest_df["agglvl_code"] = pd.to_numeric(
        latest_df["agglvl_code"], errors="coerce"
    )
    latest_df["industry_code"] = latest_df["industry_code"].astype("string").str.strip()
    latest_df["month3_emplvl"] = pd.to_numeric(
        latest_df["month3_emplvl"], errors="coerce"
    )

    # Use 2-digit sector totals where a rating maps to a whole sector. For
    # ratings that split NAICS 54 or 92, use 4-digit rows to avoid assigning
    # the same employment to both rating categories.
    detailed_targets = {
        "Professional",
        "Scientific",
        "Public_Admin",
        "National_Security",
    }
    combined_codes = {
        "31-33": {"31", "32", "33"},
        "44-45": {"44", "45"},
        "48-49": {"48", "49"},
    }
    grouped = []

    for target_code, naics_codes in TARGET_CODE_TO_NAICS.items():
        aggregation_level = (
            AGGLVL_NAICS_4DIGIT
            if target_code in detailed_targets
            else AGGLVL_NAICS_SECTOR
        )
        sectors = latest_df.loc[latest_df["agglvl_code"] == aggregation_level].copy()
        matches = sectors["industry_code"].str.startswith(
            tuple(naics_codes), na=False
        )
        if aggregation_level == AGGLVL_NAICS_SECTOR:
            matches |= sectors["industry_code"].map(
                lambda code: bool(combined_codes.get(code, set()) & set(naics_codes))
            )
        sectors = sectors.loc[matches, ["county_name", "month3_emplvl"]].copy()
        if sectors.empty:
            continue
        sectors["target_code"] = target_code
        grouped.append(sectors)

    if not grouped:
        return pd.DataFrame(columns=result_columns)

    employment = pd.concat(grouped, ignore_index=True)
    return (
        employment.groupby(["county_name", "target_code"])["month3_emplvl"]
        .sum(min_count=1)
        .rename("number_of_workers")
        .reset_index()
    )