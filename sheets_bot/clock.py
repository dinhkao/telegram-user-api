"""Asia/Bangkok time helpers for sheet names and timestamps."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .parse import format_date_ddmmyyyy, format_iso_with_offset

_TZ = ZoneInfo("Asia/Bangkok")


def bangkok_now() -> datetime:
    return datetime.now(_TZ)


def bangkok_from_datetime(dt: datetime) -> datetime:
    return dt.astimezone(_TZ)


def get_sheet_context() -> dict:
    now = bangkok_now()
    return {
        "sheet_name": format_date_ddmmyyyy(now),
        "timestamp": format_iso_with_offset(now),
    }


def format_timestamp_from_datetime(dt) -> str:
    if not dt:
        return ""
    return format_iso_with_offset(bangkok_from_datetime(dt))
