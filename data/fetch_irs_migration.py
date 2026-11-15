# IRS migration fetcher: downloads county-to-county migration data from the IRS
# Statistics of Income (SOI) and produces one net-migration row per UP county.
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

# Sets the cache location and the IRS codes used to find each county's rows.
CACHE_DIR = Path(__file__).parent / "cache"
IRS_CACHE = CACHE_DIR / "qcew_irs_migration.parquet"

MICHIGAN_STATE_FIPS = 26
TOTAL_MIGRATION_STATE_FIPS = 96  # IRS sentinel: aggregate across US + Foreign origins
TOTAL_MIGRATION_COUNTY_FIPS = 0


# Downloads one IRS SOI CSV file and returns it as a DataFrame.
def _download_csv(url: str) -> pd.DataFrame:
    """GET the url with a 60-second timeout, raising on an HTTP error status.

    The response bytes are parsed with pd.read_csv using latin-1 encoding,
    which the IRS files require.
    """
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return pd.read_csv(io.BytesIO(resp.content), encoding="latin-1")


# Returns the 3-digit county FIPS code for a county name in COUNTIES.
def _county_fips_from_name(name: str) -> int:
    """Search COUNTIES (full FIPS -> name) for the name and return its last 3 digits.

    Raises KeyError if the name isn't found.
    """
    for full_fips, county_name in COUNTIES.items():
        if county_name == name:
            return int(full_fips[2:])  # last 3 digits
    raise KeyError(name)


# Returns one county's migration counts (people moving in, people moving out,
# and the net) taken from the IRS "Total Migration-US and Foreign" summary
# rows. Returns an empty dict if either summary row is missing.
def _net_for_county(
    inflow: pd.DataFrame, outflow: pd.DataFrame, county_fips: int
) -> dict:
    """Select the county's summary row in each file, then subtract outflow from inflow.

    In the inflow file, the county is the destination (y2) and the origin (y1)
    is the total-migration sentinel (state 96, county 0). In the outflow file,
    the county is the origin (y1) and the destination (y2) is the sentinel. It
    reads the n2 column (number of exemptions, used as a count of people) from
    the first matching row in each file. Returns inflow_n2, outflow_n2, and
    net_exemptions (inflow minus outflow).
    """
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


# Downloads the IRS inflow and outflow files for the latest year-pair and
# returns a DataFrame with one row per county. Returns an empty DataFrame if
# either download fails.
def _fetch_from_irs() -> pd.DataFrame:
    """Build both URLs from IRS_SOI_BASE_URL, download them, and loop over COUNTIES.

    The file names are countyinflow{yp}.csv and countyoutflow{yp}.csv, where
    yp is LATEST_IRS_YEAR_PAIR. Any exception during the downloads returns an
    empty DataFrame silently. For each county, _net_for_county supplies the
    counts; counties with no summary rows are skipped. Each row is tagged with
    county_name and tax_year, which is 2000 plus the last two digits of the
    year-pair (the destination year of the flow).
    """
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


# Returns net migration (US and foreign combined) for each UP county for the
# latest year-pair, using the cache when it exists and fetching from the IRS
# only when it doesn't.
def fetch_irs_migration() -> pd.DataFrame:
    """Return the cache if present; otherwise fetch from the IRS and cache the result.

    There is no freshness check: any existing cache is returned as is, even if
    LATEST_IRS_YEAR_PAIR has changed since it was written. When there is no
    cache, it calls _fetch_from_irs and saves the result only if it is
    non-empty, so a failed fetch is never cached.
    """
    if IRS_CACHE.exists():
        return pd.read_parquet(IRS_CACHE)
    df = _fetch_from_irs()
    if not df.empty:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(IRS_CACHE, index=False)
    return df
