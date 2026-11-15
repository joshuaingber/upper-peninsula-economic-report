# FRED client: fetches county-level real GDP and unemployment-rate series for
# the Upper Peninsula counties, with a committed parquet cache as a fallback.
"""
Reads FRED_API_KEY from the environment (a local .env is loaded if
python-dotenv is installed).

Each series is downloaded by _fred_observations and retried with exponential
backoff by _fetch_one. _fetch_series_set spaces the per-county requests out to
stay under FRED's burst rate limit. _fetch_with_cache_fallback saves each
successful fetch to a parquet cache and reads it back if a fresh fetch fails.
If there is neither fresh data nor a cache, the public fetch functions return
an empty DataFrame so the secondary KPI row degrades to "—".
"""
# Imports
from __future__ import annotations

import io
import os
import time
from functools import lru_cache
from pathlib import Path

import pandas as pd
import requests

# Load a local .env (FRED_API_KEY=...) if present, so contributors don't have to
# export the variable by hand. Optional: if python-dotenv isn't installed, or no
# .env exists, we fall back to whatever is already in the environment.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from data.constants import FRED_API_BASE, FRED_GDP_SERIES, FRED_UNRATE_SERIES

# Sets the cache paths for the two FRED series we fetch.
# The cache is a fallback, not a short-circuit: we always try a fresh fetch
# first, and only fall back to the last-good cache if that fails. Fresh fetches
# overwrite the cache, so the fallback stays current between outages.
from data.constants import CACHE_DIR
GDP_CACHE = CACHE_DIR / "qcew_fred_gdp.parquet"
UNRATE_CACHE = CACHE_DIR / "qcew_fred_unrate.parquet"


# Fetches one FRED series and returns its observations as a (date, value)
# DataFrame. Returns an empty DataFrame if the series has no observations.
def _fred_observations(series_id: str, api_key: str) -> pd.DataFrame:
    """Call FRED's series/observations endpoint and tidy the response.

    Sends series_id and api_key with a 15-second timeout and raises
    requests.HTTPError on a failed request (including a 429). Keeps only the
    date and value columns, converts dates to datetimes and values to numbers
    (FRED's "." placeholder becomes NaN and is dropped), then sorts oldest to
    newest and resets the index.
    """
    url = f"{FRED_API_BASE}/series/observations"
    resp = requests.get(
        url,
        params={"series_id": series_id, "api_key": api_key, "file_type": "json"},
        timeout=15,
    )
    resp.raise_for_status()
    obs = resp.json().get("observations", [])
    if not obs:
        return pd.DataFrame(columns=["date", "value"])
    df = pd.DataFrame(obs)[["date", "value"]]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["value"]).sort_values("date").reset_index(drop=True)


# Sets the request pacing and retry limits used when fetching from FRED.
# FRED enforces a burst rate limit (nominally 120 req/min, but it 429s on much
# tighter rapid bursts). We fetch only a handful of series, so a small fixed
# gap between requests plus exponential backoff on a 429 keeps us under it.
_INTER_REQUEST_GAP = 1.0   # seconds between consecutive series requests
_MAX_ATTEMPTS = 6          # per-series tries before giving up
_BACKOFF_BASE = 1.0        # seconds; doubles each retry


# Fetches one series, retrying on any failure. Empty responses are retried too:
# our series are always populated, so an empty result is treated as a
# transient glitch, not "no data".
def _fetch_one(series_id: str, api_key: str) -> pd.DataFrame:
    """Retry _fred_observations up to _MAX_ATTEMPTS times with exponential backoff.

    The wait starts at _BACKOFF_BASE and doubles after each failed attempt,
    with no sleep after the last one. A 429 response waits for the server's
    Retry-After header instead, but only when it is a whole number; otherwise
    it uses the normal delay. All other HTTP and network errors use the normal
    delay too. Returns an empty DataFrame if every attempt fails.
    """
    delay = _BACKOFF_BASE
    for attempt in range(_MAX_ATTEMPTS):
        try:
            df = _fred_observations(series_id, api_key)
            if not df.empty:
                return df
        except requests.HTTPError as exc:
            resp = exc.response
            if resp is not None and resp.status_code == 429:
                # Respect server-provided Retry-After when present and numeric.
                retry_after = (resp.headers.get("Retry-After") or "").strip()
                wait = float(retry_after) if retry_after.isdigit() else delay
            else:
                wait = delay
        except Exception:
            wait = delay
        else:
            # Succeeded but returned no rows. Our series are always populated,
            # so an empty response means a transient hiccup — back off and retry
            # rather than accept it as "no data".
            wait = delay
        if attempt < _MAX_ATTEMPTS - 1:
            time.sleep(wait)
            delay *= 2
    return pd.DataFrame()


# Fetches every series in series_map and combines them into one long-format
# DataFrame with columns (county_name, date, value, series_id).
# Skips any county whose series fails, and returns an empty DataFrame only
# if every county fails.
def _fetch_series_set(series_map: dict[str, str], api_key: str) -> pd.DataFrame:
    """Loop over series_map one series at a time, calling _fetch_one for each.

    Sleeps _INTER_REQUEST_GAP between consecutive requests (not before the
    first) to stay under FRED's burst rate limit. Each non-empty result is
    tagged with its county_name and series_id, then all results are
    concatenated. Empty results are skipped.
    """
    frames = []
    for i, (county, sid) in enumerate(series_map.items()):
        if i:
            time.sleep(_INTER_REQUEST_GAP)
        df = _fetch_one(sid, api_key)
        if df.empty:
            # Tolerate per-county gaps: a small Upper Peninsula county may lack
            # a published real-GDP or LAUS series on FRED, and one missing
            # series shouldn't blank out the metric for the other fourteen.
            continue
        df["county_name"] = county
        df["series_id"] = sid
        frames.append(df)
    # Return empty only if every county failed, so we never cache an all-empty result.
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# Returns the FRED API key from the environment, or "" if it isn't set.
def _fred_api_key() -> str:
    """Read FRED_API_KEY from os.environ and strip surrounding whitespace."""
    return os.environ.get("FRED_API_KEY", "").strip()


# Reports whether a FRED API key is available. Public, for use by other modules.
def fred_key_configured() -> bool:
    """Return True if _fred_api_key() gives a non-empty string."""
    return bool(_fred_api_key())


# Fetches fresh data from FRED and falls back to the last-good cache if that
# fails. This decouples the FRED KPI row from the QCEW build: a FRED hiccup
# leaves last week's KPIs in place instead of blanking them or aborting the
# whole publish.
def _fetch_with_cache_fallback(
    series_map: dict[str, str], cache_path: Path
) -> pd.DataFrame:
    """Try a fresh fetch, then the cache, then give up with an empty DataFrame.

    With a key set, calls _fetch_series_set. If that returns rows, it creates
    the cache folder if needed, overwrites the parquet file at cache_path, and
    returns the fresh data. If it comes back empty (a sustained rate limit or
    a FRED outage), it reads cache_path instead when the file exists.

    Without a key (local or no-key runs) it skips the fetch and serves the
    cache if present. Returns an empty DataFrame if there is no fresh data and
    no cache.
    """
    api_key = _fred_api_key()
    if api_key:
        df = _fetch_series_set(series_map, api_key)
        if not df.empty:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            df.to_parquet(cache_path, index=False)
            return df
        # Fresh fetch failed; fall through to the last-good cache below.
    if cache_path.exists():
        return pd.read_parquet(cache_path)
    return pd.DataFrame()


# Returns annual real GDP for the UP counties, fresh from FRED with the cache
# as a fallback. Empty only when both the fetch and the cache are unavailable.
@lru_cache(maxsize=1)
def fetch_real_gdp() -> pd.DataFrame:
    """Call _fetch_with_cache_fallback with the GDP series and GDP_CACHE.

    Memoized with lru_cache, so build.py's several call sites trigger only one
    fetch per process.
    """
    return _fetch_with_cache_fallback(FRED_GDP_SERIES, GDP_CACHE)


# Returns the monthly unemployment rate (not seasonally adjusted) for the UP
# counties, fresh from FRED with the cache as a fallback. Empty only when both
# the fetch and the cache are unavailable.
@lru_cache(maxsize=1)
def fetch_unemployment_rate() -> pd.DataFrame:
    """Call _fetch_with_cache_fallback with the unemployment series and UNRATE_CACHE.

    Memoized with lru_cache, so build.py's several call sites trigger only one
    fetch per process.
    """
    return _fetch_with_cache_fallback(FRED_UNRATE_SERIES, UNRATE_CACHE)