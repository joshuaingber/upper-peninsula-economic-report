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
)


# Project-wide quarter-to-month convention: Q1→Feb, Q2→May, Q3→Aug, Q4→Nov.
# Mid-quarter dates so quarterly time-series points sit on the right calendar grid.
QUARTER_TO_MONTH = {1: 2, 2: 5, 3: 8, 4: 11}


def add_date_column(df: pd.DataFrame) -> pd.DataFrame:
    """Add a `date` column from `year` + `qtr` using the project's mid-quarter convention.

    Returns a copy of df with the new column appended. Used by clean() (county data)
    and get_national_qoq_pct() so the date convention has a single source of truth.
    """
    df = df.copy()
    df["date"] = pd.to_datetime(
        df["year"].astype(int).astype(str) + "-"
        + df["qtr"].map(QUARTER_TO_MONTH).astype(str) + "-01"
    )
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Full cleaning pipeline: types, derived fields, industry labels."""
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

def get_total_covered(df: pd.DataFrame) -> pd.DataFrame:
    """Total covered employment (own_code=0, agglvl=70)."""
    return df[(df["own_code"] == 0) & (df["agglvl_code"] == AGGLVL_TOTAL)]


def get_naics_sectors(df: pd.DataFrame, own_code: int = 5) -> pd.DataFrame:
    """NAICS 2-digit sector data (agglvl=74) for a given ownership type."""
    return df[(df["own_code"] == own_code) & (df["agglvl_code"] == AGGLVL_NAICS_SECTOR)]


def get_latest_quarter(df: pd.DataFrame) -> pd.DataFrame:
    """Filter to the most recent quarter available in the data."""
    if df.empty:
        return df
    max_date = df["date"].max()
    return df[df["date"] == max_date]


def latest_county_summaries(df: pd.DataFrame) -> pd.DataFrame:
    """One row per county summarizing its latest-quarter total-covered QCEW.

    Each county is reduced to the most recent quarter for which it has a
    total-covered (own_code=0, agglvl=70) row. Returns columns:
    county_name, area_fips, year, qtr, employment, qtrly_estabs,
    avg_annual_wage, oty_emp_pct, oty_estab_pct, oty_wage_pct, is_suppressed.

    Counties with no total-covered data are omitted. Shared by the Upper
    Peninsula county map and the top-counties growth chart.
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


def get_growth_quadrant_data(df: pd.DataFrame) -> pd.DataFrame:
    """Latest-quarter NAICS sectors with valid YoY employment + wage growth rates."""
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


def latest_gdp_with_growth(df_gdp: pd.DataFrame, county_name: str) -> dict:
    """Latest annual real GDP and YoY growth rate for one county.

    Returns {} when fewer than 2 observations exist (can't compute YoY).
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


def latest_unrate_with_yoy(df_unrate: pd.DataFrame, county_name: str) -> dict:
    """Latest monthly unemployment rate + YoY pp delta for one county.

    The FRED LAUS series for these counties are NSA (not seasonally adjusted),
    so YoY uses a same-month-one-year-prior comparison. Matching is by
    month-precision date (to_period("M")) rather than positional indexing,
    so a gap in the monthly series — e.g., the Oct 2025 FRED outage caused
    by the BLS appropriations lapse — never silently shifts the comparison
    window. If the prior-year same month is missing, returns {} so the cell
    falls back to "—".
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


def latest_irs_net(df_irs: pd.DataFrame, county_name: str) -> dict:
    """Most recent IRS SOI net migration figure (US + Foreign) for one county.

    Returns both endpoints of the migration window (origin_year, dest_year) so
    the display can label the figure as a two-year flow rather than collapsing
    it to a single year. tax_year is retained for backward compatibility.
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


def get_employment_treemap_data(
    df: pd.DataFrame, year: Optional[int] = None
) -> pd.DataFrame:
    """Treemap snapshot for one quarter.

    `year=None` returns the absolute latest quarter (the default behavior).
    `year=YYYY` returns the latest quarter within that year.

    Filters to own_code=5 (private), drops suppressed/Unclassified rows and
    sectors with zero employment. Returns industry_label, employment,
    qtrly_estabs, avg_annual_wage, share, year, qtr — one row per disclosable
    sector, sorted by employment desc.
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


def get_employment_treemap_years(df: pd.DataFrame) -> list[tuple[int, int]]:
    """Return [(year, latest_qtr_for_year), ...] ascending for years with disclosable data."""
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


def get_treemap_snapshots(df: pd.DataFrame) -> list:
    """All (year, latest-qtr, treemap-data) snapshots, ascending by year.

    Returns a list of (int, int, pd.DataFrame) tuples. Years whose snapshot is
    empty (e.g., universally suppressed) are dropped so the caller never has
    to render a button with no underlying data. Callers that want the most
    recent snapshot use `snapshots[-1]`.
    """
    years_asc = get_employment_treemap_years(df)
    snapshots = []
    for year, qtr in years_asc:
        snap = get_employment_treemap_data(df, year=year)
        if not snap.empty:
            snapshots.append((year, qtr, snap))
    return snapshots


def get_national_qoq_pct(df_national: pd.DataFrame, own_code: int = 5) -> pd.Series:
    """U.S. quarterly QoQ percent change in establishment count for one ownership type.

    Defaults to private (own_code=5) so the firm-formation benchmark is
    apples-to-apples with the county's private-only industry data. Pass
    own_code=0 to get the all-ownership total covered series. Input is
    expected to contain both ownership slices per fetch_national_data's
    expanded filter — older caches without the requested slice return an
    empty Series and downstream consumers degrade gracefully.

    Returns a date-indexed Series of pct change in qtrly_estabs; the first
    quarter drops out (no prior).
    """
    if df_national.empty or "qtrly_estabs" not in df_national.columns:
        return pd.Series(dtype=float)
    df = df_national[df_national["own_code"] == own_code]
    if df.empty:
        return pd.Series(dtype=float)
    df = add_date_column(df).sort_values("date").set_index("date")
    return df["qtrly_estabs"].pct_change().dropna()


def get_firm_formation_data(df: pd.DataFrame) -> pd.DataFrame:
    """Quarterly establishment churn decomposed into industries gaining and losing firms.

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

    Returns a DataFrame indexed by quarter with columns date, year_qtr, additions,
    subtractions, net. The first quarter in the input series is dropped (no QoQ
    change available).

    Note: this is *not* gross firm openings/closings (BLS doesn't publish those at
    the county level). It's the county-private establishment change, with an
    industry-level decomposition layered on top.
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
