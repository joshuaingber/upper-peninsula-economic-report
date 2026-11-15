# TODO
## List
- Find 5 potential new data sets (in progress - Z)
    - Take up_housing.parquet to visualization
- Extend pipeline.md documentation and in line comments
- Review current cache data to exhaust possible uses
    - provide summary for industry across all UP counties

## Proposed datasets
- U.S. Census Bureau — Annual Survey of State & Local Government Finances
    - website: https://www.census.gov/programs-surveys/gov-finances.html
    - data: https://www.census.gov/data/developers/data-sets/govslocalfin.html
    - contents: could be used to measure the size and composition of local government activity in each county.

- U.S. Census Bureau — American Community Survey (ACS)
    - website: https://www.census.gov/data/developers/data-sets/acs-5year.html
    - data: https://www.census.gov/acs/www/data/data-tables-and-tools/data-profiles/
    - contents: could be used to track housing prices of time, total units, occupied vs vacant, owner vs renter, seasonal/recreational/occasional vs year-around units

## Fixes
- clean.py clean_qcew_data_for_AI_risk_embed() getting sum of month3_emplvl of the latest quarter
