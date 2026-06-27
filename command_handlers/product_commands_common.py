from __future__ import annotations

from .thread_utils import extract_thread_id


def money(n: int) -> str:
    return f"{n:,}đ"


def profit(n: int) -> str:
    return f"+{n:,}đ" if n > 0 else f"{n:,}đ" if n < 0 else "0đ"

