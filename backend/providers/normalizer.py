"""
Data Normalization Utilities
============================

Shared parsing and normalization functions used by all providers.
This ensures consistent data handling regardless of source.
"""

from typing import Optional, Dict, List


def normalize_string(value) -> Optional[str]:
    """Normalize a string value, returning None for empty/null."""
    if value is None:
        return None
    value = str(value).strip()
    if value.lower() in ("", "null", "none", "n/a", "na", "-"):
        return None
    return value


def parse_amount(value) -> Optional[float]:
    """Parse a monetary amount string to float."""
    if not value:
        return None
    try:
        cleaned = (
            str(value)
            .replace("₹", "")
            .replace(",", "")
            .replace(" ", "")
            .replace("'", "")
            .replace("₹", "")
        )
        if cleaned.lower() in ("", "null", "none", "n/a", "na"):
            return None
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def parse_percentage(value) -> Optional[float]:
    """Parse a percentage string to float."""
    if not value:
        return None
    try:
        cleaned = str(value).replace("%", "").replace(" ", "")
        if cleaned.lower() in ("", "null", "none", "n/a", "na"):
            return None
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def normalize_state(state: str) -> str:
    """Normalize Indian state/UT name."""
    if not state:
        return ""
    return state.strip().title()


def parse_int(value) -> Optional[int]:
    """Parse an integer value safely."""
    if not value:
        return None
    try:
        cleaned = str(value).strip().replace(",", "")
        if cleaned.lower() in ("", "null", "none", "n/a", "na"):
            return None
        return int(float(cleaned))
    except (ValueError, TypeError):
        return None


# ─── Column Mapping Detection ──────────────────────────────────

# Canonical field names and their common CSV header variants
FIELD_PATTERNS: Dict[str, List[str]] = {
    "id": ["id", "project_id", "projectid", "sl_no", "serial_no"],
    "project_name": [
        "project_name", "name", "work", "work_name", "work_description",
        "project", "title", "description",
    ],
    "state": ["state", "state_name", "st"],
    "district": ["district", "dist", "district_name"],
    "constituency": [
        "constituency", "const", "parliamentary_constituency", "pc",
    ],
    "project_type": [
        "project_type", "type", "category", "work_type",
        "nature_of_work", "project_category",
    ],
    "sanctioned_amount": [
        "sanctioned_amount", "allocation_amount", "amount",
        "sanctioned", "allocated", "fund", "fund_allocated",
        "recommended_amount", "total_amount",
    ],
    "expenditure": [
        "expenditure", "expenditure_amount", "spent",
        "total_expenditure", "amount_spent", "expend",
    ],
    "completion_percentage": [
        "completion_percentage", "progress", "physical_progress",
        "completion", "completion_pct", "progress_percentage",
    ],
    "status": ["status", "project_status", "work_status"],
    "fy": ["fy", "financial_year", "year", "fiscal_year", "period"],
}


def detect_column_mapping(headers: List[str]) -> Dict[str, Optional[str]]:
    """
    Auto-detect CSV column mapping from headers.

    Returns a dict mapping canonical field names to the actual
    CSV header that was matched (or None if not found).
    """
    mapping = {field: None for field in FIELD_PATTERNS}

    normalized = {
        h.lower().strip().replace(" ", "_").replace("-", "_"): h
        for h in headers
    }

    for field, patterns in FIELD_PATTERNS.items():
        for pattern in patterns:
            if pattern in normalized:
                mapping[field] = normalized[pattern]
                break

    return mapping
