"""
IRS Statistics of Income (SOI) county-to-county migration fetcher.

Downloads the consolidated national inflow + outflow CSV files for the latest
year-pair (per LATEST_IRS_YEAR_PAIR in data/constants.py), filters to the
"Total Migration-US and Foreign" published summary row for each county, and
writes a small parquet with one row per county. This matches the convention
used in most regional economic studies, which report migration inclusive of
foreign inflows/outflows rather than US-domestic-only.

Year-pair convention: "2223" = tax year 2022 returns vs. tax year 2023 returns
(i.e., flows that occurred between those filing years).
"""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import requests

from data.constants import IRS_SOI_BASE_URL, LATEST_IRS_YEAR_PAIR, COUNTIES

CACHE_DIR = Path(__file__).parent / "cache"
IRS_CACHE = CACHE_DIR / "qcew_irs_migration.parquet"

MICHIGAN_STATE_FIPS = 26
TOTAL_MIGRATION_STATE_FIPS = 96  # IRS sentinel: aggregate across US + Foreign origins
TOTAL_MIGRATION_COUNTY_FIPS = 0


def _download_csv(url: str) -> pd.DataFrame:
    """GET an IRS SOI CSV with mandatory latin-1 encoding."""
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return pd.read_csv(io.BytesIO(resp.content), encoding="latin-1")


def _county_fips_from_name(name: str) -> int:
    """Reverse the COUNTIES dict to get the 3-digit county FIPS for a UP county."""
    for full_fips, county_name in COUNTIES.items():
        if county_name == name:
            return int(full_fips[2:])  # last 3 digits
    raise KeyError(name)


def _net_for_county(
    inflow: pd.DataFrame, outflow: pd.DataFrame, county_fips: int
) -> dict:
    """Look up the published Total Migration-US and Foreign summary row for one county."""
    in_row = inflow[
        (inflow["y2_statefips"] == MICHIGAN_STATE_FIPS)
        & (inflow["y2_countyfips"] == county_fips)
        & (inflow["y1_statefips"] == TOTAL_MIGRATION_STATE_FIPS)
        & (inflow["y1_countyfips"] == TOTAL_MIGRATION_COUNTY_FIPS)
    ]
    out_row = outflow[
        (outflow["y1_statefips"] == MICHIGAN_STATE_FIPS)
        & (outflow["y1_countyfips"] == county_fips)
        & (outflow["y2_statefips"] == TOTAL_MIGRATION_STATE_FIPS)
        & (outflow["y2_countyfips"] == TOTAL_MIGRATION_COUNTY_FIPS)
    ]
    if in_row.empty or out_row.empty:
        return {}
    in_n2 = int(in_row["n2"].iloc[0])
    out_n2 = int(out_row["n2"].iloc[0])
    return {
        "inflow_n2": in_n2,
        "outflow_n2": out_n2,
        "net_exemptions": in_n2 - out_n2,
    }


def _fetch_from_irs() -> pd.DataFrame:
    """Pull both consolidated CSVs and extract the per-county summary rows."""
    yp = LATEST_IRS_YEAR_PAIR
    in_url = f"{IRS_SOI_BASE_URL}/countyinflow{yp}.csv"
    out_url = f"{IRS_SOI_BASE_URL}/countyoutflow{yp}.csv"

    try:
        inflow = _download_csv(in_url)
        outflow = _download_csv(out_url)
    except Exception:
        return pd.DataFrame()

    # Tax year (e.g., "2223" → 2023 = the destination year of the flow)
    tax_year = 2000 + int(yp[2:])

    rows = []
    for full_fips, county_name in COUNTIES.items():
        county_fips = int(full_fips[2:])
        rec = _net_for_county(inflow, outflow, county_fips)
        if not rec:
            continue
        rec["county_name"] = county_name
        rec["tax_year"] = tax_year
        rows.append(rec)

    return pd.DataFrame(rows)


def fetch_irs_migration() -> pd.DataFrame:
    """Cached fetch of net domestic migration per county, latest year-pair."""
    if IRS_CACHE.exists():
        return pd.read_parquet(IRS_CACHE)
    df = _fetch_from_irs()
    if not df.empty:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(IRS_CACHE, index=False)
    return df
