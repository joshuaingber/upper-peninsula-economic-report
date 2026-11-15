"""
Narrative text generation and source citations.
Template-based descriptive paragraphs — no LLM calls.
"""
from utils.formatting import fmt_number, fmt_pct


def source_citation(name: str, url: str, frequency: str) -> str:
    """Return a source citation string for st.caption()."""
    return f"Source: [{name}]({url}) — {frequency}"


def format_industry_list(names: list[str]) -> str:
    """Join 1, 2, or 3+ industry names with correct comma/conjunction usage."""
    if len(names) == 0:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def narrate_employment_trends(
    county_name: str,
    start_year: int,
    end_year: int,
    start_empl: float,
    end_empl: float,
) -> str:
    """Describe employment level change over a multi-year period."""
    if start_empl is None or end_empl is None or start_empl == 0:
        return (
            f"Between {start_year} and {end_year}, employment data for "
            f"{county_name} is incomplete."
        )
    change_pct = (end_empl - start_empl) / start_empl * 100
    direction = "an increase" if change_pct >= 0 else "a decrease"
    return (
        f"Between {start_year} and {end_year}, employment in {county_name} "
        f"went from {fmt_number(start_empl)} to {fmt_number(end_empl)}, "
        f"{direction} of {fmt_pct(abs(change_pct))}."
    )

def narrate_median_house_value_trends(
    county_name: str,
    start_year: int,
    end_year: int,
    start_value: float,
    end_value: float,
) -> str:
    """Describe median house value change over a multi-year period."""
    if start_value is None or end_value is None or start_value == 0:
        return (
            f"Between {start_year} and {end_year}, median house value data for "
            f"{county_name} is incomplete."
        )
    change_pct = (end_value - start_value) / start_value * 100
    direction = "an increase" if change_pct >= 0 else "a decrease"
    return (
        f"Between {start_year} and {end_year}, the median house value in {county_name} "
        f"went from {fmt_number(start_value)} to {fmt_number(end_value)}, "
        f"{direction} of {fmt_pct(abs(change_pct))}."
    )