"""Date parsing and daily-sheet-name derivation."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .constants import DATE_HEADER, HEADERS


def format_sheet_name_from_date(raw: Any) -> str | None:
    """Parse a `d/m/yyyy` (or `-` separated) date into `DD/MM/YYYY`."""
    if not raw:
        return None
    m = re.match(r"^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})$", str(raw).strip())
    if not m:
        return None
    day, month, year = m.group(1), m.group(2), m.group(3)
    day = day.zfill(2)
    month = month.zfill(2)
    if len(year) == 2:
        year = f"20{year}"
    elif len(year) != 4:
        return None
    return f"{day}/{month}/{year}"


def format_sheet_name_from_compact_date(raw: Any) -> str | None:
    """Parse `DDMMYYYY` -> `DD/MM/YYYY`."""
    if not raw:
        return None
    cleaned = str(raw).strip()
    if not re.match(r"^\d{8}$", cleaned):
        return None
    return f"{cleaned[0:2]}/{cleaned[2:4]}/{cleaned[4:8]}"


def get_sheet_name_from_rows(rows: list) -> str | None:
    try:
        date_idx = HEADERS.index(DATE_HEADER)
    except ValueError:
        return None
    for row in rows:
        if not isinstance(row, list):
            continue
        val = row[date_idx] if len(row) > date_idx else None
        sheet_name = format_sheet_name_from_date(val)
        if sheet_name:
            return sheet_name
    return None


def format_date_ddmmyyyy(dt: datetime) -> str:
    return f"{dt.day:02d}/{dt.month:02d}/{dt.year:04d}"


def format_iso_with_offset(dt: datetime, offset: str = "+07:00") -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + offset
