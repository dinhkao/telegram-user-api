"""A1-notation / column-letter and header-comparison helpers."""

from __future__ import annotations

from typing import Any

from .constants import HEADERS


def end_column_letter() -> str:
    return chr(ord("A") + len(HEADERS) - 1)


def column_letter(idx: int) -> str:
    return chr(ord("A") + idx)


def a1(sheet_name: str, rng: str) -> str:
    escaped = (sheet_name or "").replace("'", "''")
    return f"'{escaped}'!{rng}"


def normalize_header_cell(cell: Any) -> str:
    return ("" if cell is None else str(cell)).strip()


def headers_match(current_header: list, expected_header: list) -> bool:
    if len(current_header) != len(expected_header):
        return False
    for i in range(len(expected_header)):
        if normalize_header_cell(current_header[i]) != expected_header[i]:
            return False
    return True


def contains_all_headers(header_row: list, names: list) -> bool:
    return all(name in header_row for name in names)
