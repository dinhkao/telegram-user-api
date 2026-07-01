"""sheets_bot.parse — PURE functions (no network / no IO), aggregated.

Each submodule owns one concern; this package re-exports the public surface so
callers can keep using `from sheets_bot import parse; parse.build_html(...)`.
"""

from .columns import (
    a1,
    column_letter,
    contains_all_headers,
    end_column_letter,
    headers_match,
    normalize_header_cell,
)
from .constants import (
    ARRAY_FORMULAS,
    DATE_HEADER,
    HEADERS,
    HIDDEN_EXPORT_HEADERS,
    MANAGED_HEADER_MARKERS,
    NEW_COLUMNS_BEFORE_LINK,
)
from .dates import (
    format_date_ddmmyyyy,
    format_iso_with_offset,
    format_sheet_name_from_compact_date,
    format_sheet_name_from_date,
    get_sheet_name_from_rows,
)
from .escape import escape_html, is_finite_number
from .export import (
    filter_export_columns,
    format_import_row_message,
    trim_trailing_empty_rows,
)
from .gviz import get_gviz_cell_value, parse_gviz_response
from .html import build_html
from .payload import normalize_product_code, parse_leading_amount, parse_quoted_payload
from .refs import build_hyperlink_formula, build_sheet_row_url, escape_formula_string

__all__ = [
    "a1", "column_letter", "contains_all_headers", "end_column_letter",
    "headers_match", "normalize_header_cell", "ARRAY_FORMULAS", "DATE_HEADER",
    "HEADERS", "HIDDEN_EXPORT_HEADERS", "MANAGED_HEADER_MARKERS",
    "NEW_COLUMNS_BEFORE_LINK", "format_date_ddmmyyyy", "format_iso_with_offset",
    "format_sheet_name_from_compact_date", "format_sheet_name_from_date",
    "get_sheet_name_from_rows", "escape_html", "is_finite_number",
    "filter_export_columns", "format_import_row_message", "trim_trailing_empty_rows",
    "get_gviz_cell_value", "parse_gviz_response", "build_html",
    "normalize_product_code", "parse_leading_amount", "parse_quoted_payload",
    "build_hyperlink_formula", "build_sheet_row_url", "escape_formula_string",
]
