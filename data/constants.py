"""
Constants for the Upper Peninsula Regional Economic Dashboard.
FIPS codes, NAICS labels, ownership codes, color palettes, and API config.

Adapted from Bryan Cutsinger's South Florida Economic Report
(https://github.com/bryanpcutsinger/south-florida-economic-report, MIT).
The geography here is the 15 counties of Michigan's Upper Peninsula; branding
follows the Northern Michigan University palette.
"""
from datetime import date

# ── BLS QCEW API ──────────────────────────────────────────────────────────────
BLS_BASE_URL = "https://data.bls.gov/cew/data/api/{year}/{quarter}/area/{fips}.csv"

# Year range: 2019 through current year (API returns 404 for unpublished quarters)
START_YEAR = 2019
END_YEAR = date.today().year
YEARS = list(range(START_YEAR, END_YEAR + 1))
QUARTERS = [1, 2, 3, 4]

# ── Counties ──────────────────────────────────────────────────────────────────
# The 15 counties of Michigan's Upper Peninsula (state FIPS 26). Ordered
# geographically west → east so dropdowns and legends read sensibly.
COUNTIES = {
    "26053": "Gogebic",
    "26131": "Ontonagon",
    "26071": "Iron",
    "26061": "Houghton",
    "26083": "Keweenaw",
    "26013": "Baraga",
    "26043": "Dickinson",
    "26109": "Menominee",
    "26103": "Marquette",
    "26003": "Alger",
    "26041": "Delta",
    "26153": "Schoolcraft",
    "26095": "Luce",
    "26097": "Mackinac",
    "26033": "Chippewa",
}

# State FIPS shared by every UP county — used by the choropleth and the IRS
# migration filter.
STATE_FIPS = "26"

# ── Northern Michigan University Color Palette ───────────────────────────────
# Primary brand marks (NMU Institutional Brand Standards):
#   NMU Green  #095339  (Pantone 343 C)
#   NMU Gold   #FFC425  (Pantone 123 C)
# Supporting neutrals/accents are brand-compatible derivations; a true semantic
# red is retained for "negative" deltas regardless of brand (lower-is-worse).
NMU_GREEN = "#095339"
NMU_GOLD = "#FFC425"
NMU_LIGHT_GREEN = "#3F7E5E"
NMU_DARK_GRAY = "#3D3D3D"
NMU_GRAY = "#CCCCCC"
NMU_STONE = "#7E8C84"
NMU_PALE_GREEN = "#E3EFE8"
NMU_SAND = "#D4B98B"
SEMANTIC_RED = "#C8102E"

# Backward-compatible aliases. The components import these `FAU_*` names; rather
# than rename every import, we re-point the names at the NMU palette so the whole
# app re-skins from one place. (Names kept for diff minimalism, values are NMU.)
FAU_BLUE = NMU_GREEN
FAU_RED = SEMANTIC_RED
FAU_DARK_GRAY = NMU_DARK_GRAY
FAU_GRAY = NMU_GRAY
FAU_ELECTRIC_BLUE = NMU_GOLD
FAU_STONE = NMU_STONE
FAU_SKY_BLUE = NMU_PALE_GREEN
FAU_SAND = NMU_SAND

# Per-county identity colors for the single-county trend charts. Fifteen counties
# don't get fifteen meaningfully distinct hues, so we cycle a small NMU-derived
# qualitative set; the map and top-counties charts carry their own color logic.
_COUNTY_PALETTE = [
    NMU_GREEN, NMU_GOLD, NMU_LIGHT_GREEN, NMU_STONE, NMU_SAND,
    NMU_DARK_GRAY, SEMANTIC_RED,
]
COUNTY_COLORS = {
    name: _COUNTY_PALETTE[i % len(_COUNTY_PALETTE)]
    for i, name in enumerate(COUNTIES.values())
}

# Diverging color scale for the choropleth map (OTY employment % change):
# red (decline) → pale → NMU green (growth).
MAP_DIVERGING_SCALE = [
    [0.0, SEMANTIC_RED],
    [0.5, NMU_PALE_GREEN],
    [1.0, NMU_GREEN],
]

# Industry → NMU palette color, grouped by broad domain. Used by the Growth
# Quadrant chart, which colors bubbles by domain rather than by county.
INDUSTRY_DOMAIN_COLORS = {
    # Goods-producing
    "Agriculture":                       FAU_RED,
    "Mining":                            FAU_RED,
    "Utilities":                         FAU_RED,
    "Construction":                      FAU_RED,
    "Manufacturing":                     FAU_RED,
    # Trade & Logistics
    "Wholesale Trade":                   FAU_SAND,
    "Retail Trade":                      FAU_SAND,
    "Transportation & Warehousing":      FAU_SAND,
    # Information & Finance
    "Information":                       FAU_BLUE,
    "Finance & Insurance":               FAU_BLUE,
    "Real Estate":                       FAU_BLUE,
    # Professional & Business
    "Professional & Technical Services": FAU_ELECTRIC_BLUE,
    "Management of Companies":           FAU_ELECTRIC_BLUE,
    "Admin & Waste Services":            FAU_ELECTRIC_BLUE,
    # Education & Health
    "Educational Services":              FAU_STONE,
    "Health Care & Social Assistance":   FAU_STONE,
    # Leisure & Other
    "Arts & Entertainment":              FAU_DARK_GRAY,
    "Accommodation & Food Services":     FAU_DARK_GRAY,
    "Other Services":                    FAU_DARK_GRAY,
    "Public Administration":             FAU_DARK_GRAY,
}

# ── Aggregation levels ────────────────────────────────────────────────────────
# 70 = Total, all industries (own_code 0 only)
# 71 = Total, all industries by ownership
# 72 = Supersector (NAICS domain)
# 73 = Supersector subdivision
# 74 = NAICS Sector (2-digit)
# 75 = NAICS 3-digit
# 76 = NAICS 4-digit
# 77 = NAICS 5-digit
# 78 = NAICS 6-digit
AGGLVL_US_TOTAL = 10       # U.S. national total (only valid for area_fips=US000)
AGGLVL_US_BY_OWN = 11      # U.S. total by ownership; rows for own_codes 1, 2, 3, 5


# ── External (non-QCEW) data sources ─────────────────────────────────────────
# These power the second row of metrics on each county's KPI card.

FRED_API_BASE = "https://api.stlouisfed.org/fred"

# Real GDP series (annual, thousands of chained 2017 dollars). BEA publishes
# real GDP for every county; FRED mirrors it as REALGDPALL{5-digit FIPS}, so
# the series IDs are fully FIPS-derivable.
FRED_GDP_SERIES = {
    name: f"REALGDPALL{fips}" for fips, name in COUNTIES.items()
}

# Unemployment rate series (monthly %, NSA). These are FRED's curated
# county series ({state}{county-abbrev}{n}URN) and are NOT derivable from FIPS
# — they were resolved via FRED search (title "Unemployment Rate in <County>
# County, MI", monthly, NSA) and verified against the API. The FIPS-derivable
# LAUCN{fips}0000000003 family only carries the ANNUAL rate (…03A) at the
# county level, not a monthly one, so the curated URN series are used instead.
# Bump an ID here if FRED renames it. fetch_fred tolerates a missing county.
FRED_UNRATE_SERIES = {
    "Gogebic":     "MIGOGE3URN",
    "Ontonagon":   "MIONTO1URN",
    "Iron":        "MIIRON1URN",
    "Houghton":    "MIHOUG1URN",
    "Keweenaw":    "MIKEWE3URN",
    "Baraga":      "MIBARA3URN",
    "Dickinson":   "MIDICK3URN",
    "Menominee":   "MIMENO9URN",
    "Marquette":   "MIMARQ5URN",
    "Alger":       "MIALGE3URN",
    "Delta":       "MIDELT1URN",
    "Schoolcraft": "MISCHO3URN",
    "Luce":        "MILUCE5URN",
    "Mackinac":    "MIMACK7URN",
    "Chippewa":    "MICHIP3URN",
}

# IRS Statistics of Income county-to-county migration data. Year pair is the
# tax-year transition (e.g., "2223" = 2022→2023 flows). Bump explicitly when
# IRS publishes a newer year so the version change is visible in git.
IRS_SOI_BASE_URL = "https://www.irs.gov/pub/irs-soi"
LATEST_IRS_YEAR_PAIR = "2223"
AGGLVL_TOTAL = 70          # Single-area total covered, own_code=0
AGGLVL_TOTAL_BY_OWN = 71   # Total by ownership
AGGLVL_SUPERSECTOR = 72    # Supersector by ownership
AGGLVL_NAICS_SECTOR = 74   # 2-digit NAICS sector by ownership
AGGLVL_NAICS_4DIGIT = 76   # 4-digit NAICS industry by ownership

# ── Supersector labels (own_code 5 = private) ────────────────────────────────
SUPERSECTOR_LABELS = {
    "11":    "Agriculture",
    "21":    "Mining",
    "22":    "Utilities",
    "23":    "Construction",
    "31-33": "Manufacturing",
    "42":    "Wholesale Trade",
    "44-45": "Retail Trade",
    "48-49": "Transportation & Warehousing",
    "51":    "Information",
    "52":    "Finance & Insurance",
    "53":    "Real Estate",
    "54":    "Professional & Technical Services",
    "55":    "Management of Companies",
    "56":    "Admin & Waste Services",
    "61":    "Educational Services",
    "62":    "Health Care & Social Assistance",
    "71":    "Arts & Entertainment",
    "72":    "Accommodation & Food Services",
    "81":    "Other Services",
    "92":    "Public Administration",
    "99":    "Unclassified",
}

# Supersector codes used by each ownership type at agglvl 72
# (subset varies by ownership; own_code 5 has the broadest private set)
SUPERSECTOR_DOMAIN_CODES = {
    "101": "Goods-producing",
    "102": "Service-providing",
    "1011": "Natural Resources & Mining",
    "1012": "Construction",
    "1013": "Manufacturing",
    "1021": "Trade, Transportation & Utilities",
    "1022": "Information",
    "1023": "Financial Activities",
    "1024": "Professional & Business Services",
    "1025": "Education & Health Services",
    "1026": "Leisure & Hospitality",
    "1027": "Other Services",
    "1028": "Public Administration",
    "1029": "Unclassified",
}

# ── Numeric columns that need type conversion ─────────────────────────────────
NUMERIC_COLS = [
    "own_code", "agglvl_code", "size_code", "year", "qtr",
    "qtrly_estabs",
    "month1_emplvl", "month2_emplvl", "month3_emplvl",
    "total_qtrly_wages", "taxable_qtrly_wages", "qtrly_contributions",
    "avg_wkly_wage",
    "lq_qtrly_estabs",
    "lq_month1_emplvl", "lq_month2_emplvl", "lq_month3_emplvl",
    "lq_total_qtrly_wages", "lq_taxable_qtrly_wages",
    "lq_qtrly_contributions", "lq_avg_wkly_wage",
    "oty_qtrly_estabs_chg", "oty_qtrly_estabs_pct_chg",
    "oty_month1_emplvl_chg", "oty_month1_emplvl_pct_chg",
    "oty_month2_emplvl_chg", "oty_month2_emplvl_pct_chg",
    "oty_month3_emplvl_chg", "oty_month3_emplvl_pct_chg",
    "oty_total_qtrly_wages_chg", "oty_total_qtrly_wages_pct_chg",
    "oty_taxable_qtrly_wages_chg", "oty_taxable_qtrly_wages_pct_chg",
    "oty_qtrly_contributions_chg", "oty_qtrly_contributions_pct_chg",
    "oty_avg_wkly_wage_chg", "oty_avg_wkly_wage_pct_chg",
]

