# QCEW fetcher: downloads quarterly county-level (and U.S. national) employment
# and wage data from BLS and caches it locally as parquet.
"""
Data comes from BLS's per-area QCEW CSV endpoint (BLS_BASE_URL), one
county-quarter file at a time. The files are combined into one DataFrame and
saved under data/cache/. Later loads read that cache instead of calling the
API, because QCEW updates quarterly with a 6-9 month lag, so there is no
reason to hit BLS on every app load. To pull new quarters, call refresh_data()
or delete the cache file.
"""
from __future__ import annotations
import io
from pathlib import Path

import pandas as pd
import requests

# Streamlit is optional: when it's installed we show a progress bar, otherwise
# progress goes to the console.
try:
    import streamlit as st
except ImportError:
    st = None

from data.constants import (
    BLS_BASE_URL, COUNTIES, YEARS, QUARTERS,
    AGGLVL_US_TOTAL, AGGLVL_US_BY_OWN, AGGLVL_STATE_TOTAL, MICHIGAN_FIPS,
)

# Sets the cache locations for the county data and the U.S. national data.
CACHE_DIR = Path(__file__).parent / "cache"
CACHE_FILE = CACHE_DIR / "qcew_data.parquet"
NATIONAL_CACHE_FILE = CACHE_DIR / "qcew_national.parquet"
STATE_CACHE_FILE = CACHE_DIR / "qcew_michigan.parquet"


# Downloads every county-quarter CSV from BLS and returns them as one
# DataFrame with an added county_name column. Returns an empty DataFrame if
# nothing could be fetched.
def _fetch_from_bls() -> pd.DataFrame:
    """Request one CSV per county, year, and quarter, then concatenate them.

    Loops over COUNTIES x YEARS x QUARTERS, building each URL from
    BLS_BASE_URL with a 30-second timeout. A response with status 200 is
    parsed with pd.read_csv and tagged with its county_name. Any other status,
    or any exception, is skipped silently. Progress is shown with a Streamlit
    progress bar when Streamlit is available, otherwise as a console counter.
    If no file was fetched, it reports an error (st.error or print) and
    returns an empty DataFrame.
    """
    frames = []
    total = len(COUNTIES) * len(YEARS) * len(QUARTERS)
    done = 0

    # Use Streamlit progress bar if available, otherwise print to console
    use_st = False
    if st is not None:
        try:
            progress = st.progress(0, text="Fetching data from BLS...")
            use_st = True
        except Exception:
            pass
    if not use_st:
        print("Fetching data from BLS...", flush=True)

    for fips in COUNTIES:
        for year in YEARS:
            for qtr in QUARTERS:
                url = BLS_BASE_URL.format(year=year, quarter=qtr, fips=fips)
                try:
                    resp = requests.get(url, timeout=30)
                    if resp.status_code == 200:
                        df = pd.read_csv(io.StringIO(resp.text))
                        df["county_name"] = COUNTIES[fips]
                        frames.append(df)
                except Exception:
                    pass
                done += 1
                if use_st:
                    progress.progress(done / total,
                                      text=f"Fetching data from BLS... ({done}/{total})")
                else:
                    print(f"\r  {done}/{total}", end="", flush=True)

    if use_st:
        progress.empty()
    else:
        print()

    if not frames:
        msg = "No data could be fetched from BLS. Please try again later."
        if use_st:
            st.error(msg)
        else:
            print(f"ERROR: {msg}")
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


# Saves the county DataFrame to the local parquet cache.
def _save_cache(df: pd.DataFrame) -> None:
    """Create CACHE_DIR if needed, then write df to CACHE_FILE without the index."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CACHE_FILE, index=False)


# Returns the cached county DataFrame, or None if there is no cache yet.
def _load_cache() -> pd.DataFrame | None:
    """Read CACHE_FILE with pd.read_parquet if the file exists, else return None."""
    if CACHE_FILE.exists():
        return pd.read_parquet(CACHE_FILE)
    return None


# Returns the county QCEW data, using the cache when it exists and fetching
# from BLS only when it doesn't.
def fetch_all_data() -> pd.DataFrame:
    """Return the cache if present; otherwise fetch from BLS and cache the result.

    There is no freshness check: any existing cache is returned as is. When
    there is no cache, it calls _fetch_from_bls and saves the result only if
    it is non-empty, so a failed fetch is never cached.
    """
    cached = _load_cache()
    if cached is not None:
        return cached

    # No cache — fetch fresh from BLS
    df = _fetch_from_bls()
    if not df.empty:
        _save_cache(df)
    return df


# Forces a fresh download of the county data and overwrites the cache.
def refresh_data() -> pd.DataFrame:
    """Call _fetch_from_bls and save the result to the cache if it is non-empty.

    A failed refresh (empty result) leaves the existing cache untouched.

    NOTE: this only refreshes the per-county cache. The national cache
    (qcew_national.parquet) is left untouched because no UI currently
    invokes refresh_data(). When a Refresh button is added to app.py,
    extend this function to also call _fetch_national_from_bls().
    """
    df = _fetch_from_bls()
    if not df.empty:
        _save_cache(df)
    return df


# ── National (US000) fetch ───────────────────────────────────────────────────


# Downloads U.S. national totals (area code US000) for each year and quarter,
# keeping two slices: all-ownership total covered employment, and private only.
# The private slice powers the firm-formation benchmark so it is apples-to-
# apples with the county's private-only industry data. Returns raw BLS columns,
# or an empty DataFrame if nothing could be fetched.
def _fetch_national_from_bls() -> pd.DataFrame:
    """Request one US000 CSV per year and quarter, filter each, and concatenate.

    Loops over YEARS x QUARTERS with a 60-second timeout, since the national
    file is larger. Each CSV is filtered to rows where (own_code=0 and
    agglvl_code=AGGLVL_US_TOTAL, i.e. 10) or (own_code=5 and
    agglvl_code=AGGLVL_US_BY_OWN, i.e. 11). Failed requests are skipped
    silently, and progress is shown the same way as in _fetch_from_bls.

    Do NOT pass the result through clean(): clean() requires the county_name
    column that only the per-county fetcher adds.
    """
    frames = []
    total = len(YEARS) * len(QUARTERS)
    done = 0

    use_st = False
    if st is not None:
        try:
            progress = st.progress(0, text="Fetching U.S. national QCEW from BLS...")
            use_st = True
        except Exception:
            pass
    if not use_st:
        print("Fetching U.S. national QCEW from BLS...", flush=True)

    for year in YEARS:
        for qtr in QUARTERS:
            url = BLS_BASE_URL.format(year=year, quarter=qtr, fips="US000")
            try:
                resp = requests.get(url, timeout=60)  # larger timeout — file is bigger
                if resp.status_code == 200:
                    df = pd.read_csv(io.StringIO(resp.text))
                    df = df[
                        ((df["own_code"] == 0) & (df["agglvl_code"] == AGGLVL_US_TOTAL))
                        | ((df["own_code"] == 5) & (df["agglvl_code"] == AGGLVL_US_BY_OWN))
                    ]
                    frames.append(df)
            except Exception:
                pass
            done += 1
            if use_st:
                progress.progress(done / total,
                                  text=f"Fetching U.S. national QCEW... ({done}/{total})")
            else:
                print(f"\r  {done}/{total}", end="", flush=True)

    if use_st:
        progress.empty()
    else:
        print()

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# Returns the national QCEW totals, using the cache when it exists and fetching
# from BLS otherwise. Returns raw BLS columns (not cleaned) for the total and
# private slices. Use data.clean.get_national_qoq_pct(df, own_code=...) to
# derive the quarter-over-quarter percent change for either slice.
def fetch_national_data() -> pd.DataFrame:
    """Load the national cache, re-fetching it if it is stale, or fetch if absent.

    If the cache file exists, it is read. A cache that has an own_code column
    but no own_code=5 rows predates the multi-ownership filter, so it is
    re-fetched and overwritten in place; if that re-fetch comes back empty,
    the old cache is returned instead. This keeps downstream code from
    silently degrading on a stale schema. If there is no cache file, it calls
    _fetch_national_from_bls and saves the result only if it is non-empty.
    """
    if NATIONAL_CACHE_FILE.exists():
        df = pd.read_parquet(NATIONAL_CACHE_FILE)
        if "own_code" in df.columns and 5 not in df["own_code"].values:
            fresh = _fetch_national_from_bls()
            if not fresh.empty:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                fresh.to_parquet(NATIONAL_CACHE_FILE, index=False)
                df = fresh
        return df
    df = _fetch_national_from_bls()
    if not df.empty:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(NATIONAL_CACHE_FILE, index=False)
    return df


# ── Michigan statewide (26000) fetch ─────────────────────────────────────────


def _fetch_state_from_bls(fips: str = MICHIGAN_FIPS) -> pd.DataFrame:
    """Fetch the statewide total-covered row (own_code=0, agglvl=50) for each quarter.

    Powers the Michigan benchmark inset on the county map. Returns RAW BLS
    columns (NOT cleaned), like the national fetch.
    """
    frames = []
    print(f"Fetching statewide QCEW ({fips}) from BLS...", flush=True)
    for year in YEARS:
        for qtr in QUARTERS:
            url = BLS_BASE_URL.format(year=year, quarter=qtr, fips=fips)
            try:
                resp = requests.get(url, timeout=60)
                if resp.status_code == 200:
                    df = pd.read_csv(io.StringIO(resp.text))
                    frames.append(df[(df["own_code"] == 0) & (df["agglvl_code"] == AGGLVL_STATE_TOTAL)])
            except Exception:
                pass
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_state_data(refresh: bool = False) -> pd.DataFrame:
    """Load Michigan statewide QCEW totals from cache, or fetch from BLS.

    Like the national cache, this file is not committed: the weekly CI build
    starts without it and fetches fresh. Pass refresh=True to re-fetch locally.
    """
    if STATE_CACHE_FILE.exists() and not refresh:
        return pd.read_parquet(STATE_CACHE_FILE)
    df = _fetch_state_from_bls()
    if not df.empty:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(STATE_CACHE_FILE, index=False)
    return df
