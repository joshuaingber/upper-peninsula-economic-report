"""
FRED API client for county-level real GDP and unemployment series.

Reads FRED_API_KEY from an environment variable. If missing or any call
fails, returns an empty DataFrame so the secondary KPI row gracefully
degrades to "—".

The per-county series are fetched back-to-back, so requests are spaced out
and retried with exponential backoff that honors FRED's 429 ``Retry-After``
header to stay under FRED's burst rate limit (see ``_fetch_one`` and
``_fetch_series_set``).
"""
from __future__ import annotations

import io
import os
import time
from pathlib import Path

import pandas as pd
import requests

from data.constants import FRED_API_BASE, FRED_GDP_SERIES, FRED_UNRATE_SERIES

CACHE_DIR = Path(__file__).parent / "cache"
GDP_CACHE = CACHE_DIR / "qcew_fred_gdp.parquet"
UNRATE_CACHE = CACHE_DIR / "qcew_fred_unrate.parquet"


def _fred_observations(series_id: str, api_key: str) -> pd.DataFrame:
    """Fetch one FRED series's observations as a (date, value) DataFrame."""
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


# FRED enforces a burst rate limit (nominally 120 req/min, but it 429s much
# tighter rapid bursts). We fetch only a handful of series, so a small fixed
# gap between requests plus exponential backoff on a 429 keeps us under it.
_INTER_REQUEST_GAP = 0.6   # seconds between consecutive series requests
_MAX_ATTEMPTS = 5          # per-series tries before giving up
_BACKOFF_BASE = 1.0        # seconds; doubles each retry


def _fetch_one(series_id: str, api_key: str) -> pd.DataFrame:
    """Fetch one series with retry + backoff, honoring 429 Retry-After.

    Returns an empty DataFrame if every attempt fails. A 429 (rate limit) is
    retried with exponential backoff; other HTTP/network errors get a short
    backoff too, since they're usually transient.
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


def _fetch_series_set(series_map: dict[str, str], api_key: str) -> pd.DataFrame:
    """Fetch all county series in long-format (county_name, date, value).

    Each series is retried with backoff (see _fetch_one), and consecutive
    requests are spaced out to stay under FRED's burst rate limit.

    Per-county tolerant: a county whose series is missing or fails is simply
    skipped, and the rest are still returned. This matters for the Upper
    Peninsula, where a small county may lack a published real-GDP or LAUS
    series on FRED — one missing series shouldn't blank out the metric for the
    other fourteen. Returns an empty DataFrame only if EVERY county fails (so
    we never persist an all-empty cache).
    """
    frames = []
    for i, (county, sid) in enumerate(series_map.items()):
        if i:
            time.sleep(_INTER_REQUEST_GAP)
        df = _fetch_one(sid, api_key)
        if df.empty:
            continue  # skip just this county; keep the rest
        df["county_name"] = county
        df["series_id"] = sid
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _fred_api_key() -> str:
    return os.environ.get("FRED_API_KEY", "").strip()


def fred_key_configured() -> bool:
    """True if a non-empty FRED_API_KEY is set — public predicate for callers."""
    return bool(_fred_api_key())


def fetch_real_gdp() -> pd.DataFrame:
    """Cached fetch of annual real GDP for the UP counties.

    Returns an empty DataFrame if no cache and no API key is set.
    """
    if GDP_CACHE.exists():
        return pd.read_parquet(GDP_CACHE)
    api_key = _fred_api_key()
    if not api_key:
        return pd.DataFrame()
    df = _fetch_series_set(FRED_GDP_SERIES, api_key)
    if not df.empty:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(GDP_CACHE, index=False)
    return df


def fetch_unemployment_rate() -> pd.DataFrame:
    """Cached fetch of monthly unemployment rate (NSA) for the UP counties.

    Returns an empty DataFrame if no cache and no API key is set.
    """
    if UNRATE_CACHE.exists():
        return pd.read_parquet(UNRATE_CACHE)
    api_key = _fred_api_key()
    if not api_key:
        return pd.DataFrame()
    df = _fetch_series_set(FRED_UNRATE_SERIES, api_key)
    if not df.empty:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(UNRATE_CACHE, index=False)
    return df
