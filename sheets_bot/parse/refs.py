"""Spreadsheet URL and HYPERLINK-formula builders."""

from __future__ import annotations

from typing import Any


def escape_formula_string(value: Any) -> str:
    return str(value if value is not None else "").replace('"', '""')


def build_sheet_row_url(spreadsheet_id: str, gid: Any, row_number: Any) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={gid}&range=A{row_number}"


def build_hyperlink_formula(url: str, label: str) -> str:
    return f'=HYPERLINK("{escape_formula_string(url)}";"{escape_formula_string(label)}")'
