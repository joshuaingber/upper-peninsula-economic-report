"""
Constants for the South Florida Regional Economic Dashboard.
FIPS codes, NAICS labels, ownership codes, color palettes, and API config.
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
COUNTIES = {
    "12099": "Palm Beach",
    "12011": "Broward",
    "12086": "Miami-Dade",
}

# ── FAU Color Palette ────────────────────────────────────────────────────────
FAU_BLUE = "#003366"
FAU_RED = "#CC0000"
FAU_DARK_GRAY = "#4D4C55"
FAU_GRAY = "#CCCCCC"
FAU_ELECTRIC_BLUE = "#126BD9"
FAU_STONE = "#7A97AB"
FAU_SKY_BLUE = "#D9ECFF"
FAU_SAND = "#D4B98B"

COUNTY_COLORS = {
    "Palm Beach": FAU_BLUE,
    "Broward": FAU_RED,
    "Miami-Dade": FAU_ELECTRIC_BLUE,
}

# Industry → FAU palette color, grouped by broad domain. Used by the Growth
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

# Real GDP series (annual, thousands of chained 2017 dollars). FIPS-derivable.
FRED_GDP_SERIES = {
    "Palm Beach": "REALGDPALL12099",
    "Broward":    "REALGDPALL12011",
    "Miami-Dade": "REALGDPALL12086",
}

# Unemployment rate series (monthly %, NSA). IDs are NOT derivable from FIPS —
# verified manually via FRED search. Bump if any series ID is renamed.
FRED_UNRATE_SERIES = {
    "Palm Beach": "FLPALM2URN",
    "Broward":    "FLBROW5URN",
    "Miami-Dade": "FLMIAM6URN",
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

