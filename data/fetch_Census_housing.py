# Fetches ACS 5-year housing data for every Upper Peninsula county and caches it as one parquet file.

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd
import requests

from data.constants import COUNTIES, STATE_FIPS, ACS_YEARS, ACS_BASE_URL, HOUSING_VARIABLES, ACS_CACHE_PATH
# Load a local .env (CENSUS_API_KEY=...) if present, so contributors don't have to
# export the variable by hand. Optional: if python-dotenv isn't installed, or no
# .env exists, we fall back to whatever is already in the environment.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# Returns ACS housing characteristics for every UP county and year as one DataFrame, cached as parquet.
def get_up_housing(refresh=False, cache_path=ACS_CACHE_PATH):
    """Returns the parquet file at cache_path if it exists, unless refresh=True.
    Otherwise it makes one ACS 5-year request per year in YEARS, asking for all
    counties in COUNTIES at once (the county codes are the last three digits of
    each 5-digit FIPS). Each JSON response becomes a DataFrame tagged with its
    year. A 404 means that release isn't published yet, so the year is skipped;
    any other HTTP error is raised. The frames are concatenated, county names
    come from COUNTIES, Census placeholder codes (negative values) become
    missing values, and the result is written to parquet before being returned.
    """
    cache_path = Path(cache_path)
    if cache_path.exists() and not refresh:
        return pd.read_parquet(cache_path)

    api_key = os.getenv("CENSUS_API_KEY")
    county_codes = ",".join(fips[2:] for fips in COUNTIES)
    frames = []

    for year in ACS_YEARS:
        params = {
            "get": ",".join(HOUSING_VARIABLES),
            "for": f"county:{county_codes}",
            "in": f"state:{STATE_FIPS}",
        }
        if api_key:
            params["key"] = api_key

        resp = requests.get(ACS_BASE_URL.format(year=year), params=params, timeout=30)
        if resp.status_code == 404:
            print(f"Skipping {year}: not published yet")
            continue
        resp.raise_for_status()



        rows = resp.json()
        df = pd.DataFrame(rows[1:], columns=rows[0])
        df["year"] = year
        frames.append(df)

    if not frames:
        raise RuntimeError("No ACS data returned for any year.")

    out = pd.concat(frames, ignore_index=True).rename(columns=HOUSING_VARIABLES)
    out["fips"] = out["state"] + out["county"]
    out["county_name"] = out["fips"].map(COUNTIES)
    out = out.drop(columns=["state", "county"])

    for col in HOUSING_VARIABLES.values():
        out[col] = pd.to_numeric(out[col], errors="coerce")
        out.loc[out[col] < 0, col] = pd.NA

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(cache_path, index=False)
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch ACS housing data for UP counties.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Fetch current Census data instead of using the cached file.",
    )
    args = parser.parse_args()
    housing = get_up_housing(refresh=args.refresh)
    print(f"Loaded {len(housing)} rows from {ACS_CACHE_PATH}")