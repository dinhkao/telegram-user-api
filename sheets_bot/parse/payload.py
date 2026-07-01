"""Parsing of user message payloads (quoted rows, leading amounts, codes)."""

from __future__ import annotations

import re
from typing import Any


def parse_quoted_payload(raw_text: str) -> list:
    """A quoted string of newline-separated, semicolon-separated rows.

    Returns list of rows, each a list of trimmed cell strings.
    """
    if not (raw_text.startswith('"') and raw_text.endswith('"')):
        return []
    inner = raw_text[1:-1]
    lines = [line.strip() for line in re.split(r"\r?\n", inner)]
    lines = [line for line in lines if line]
    return [[cell.strip() for cell in line.split(";")] for line in lines]


def parse_leading_amount(raw_text: str) -> dict | None:
    if not raw_text:
        return None
    m = re.match(r"^([+-]?\d+(?:[.,]\d+)?)(?:\s+|$)(.*)$", raw_text, re.S)
    if not m:
        return None
    raw_amount = m.group(1).replace(",", ".")
    try:
        amount = float(raw_amount)
    except ValueError:
        return None
    if amount != amount or amount in (float("inf"), float("-inf")):
        return None
    return {"amount": amount, "note": (m.group(2) or "").strip()}


def normalize_product_code(raw: Any) -> str:
    return ("" if raw is None else str(raw)).strip().lower()
