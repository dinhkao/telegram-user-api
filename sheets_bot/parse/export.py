"""Row shaping for the HTML export and import-row message formatting."""

from __future__ import annotations

from .constants import HIDDEN_EXPORT_HEADERS


def trim_trailing_empty_rows(rows: list) -> list:
    last = len(rows) - 1

    def has_content(row):
        return isinstance(row, list) and any(
            ("" if c is None else str(c)).strip() != "" for c in row
        )

    while last >= 0 and not has_content(rows[last]):
        last -= 1
    return rows[: last + 1]


def filter_export_columns(rows: list) -> list:
    if not rows:
        return rows
    header = rows[0]
    keep_idx = []
    for idx, h in enumerate(header):
        name = ("" if h is None else str(h)).strip()
        if name not in HIDDEN_EXPORT_HEADERS:
            keep_idx.append(idx)
    result = []
    for row in rows:
        result.append(
            [row[i] if (row and i < len(row) and row[i] is not None) else "" for i in keep_idx]
        )
    return result


def format_import_row_message(values: list) -> str:
    if not values:
        return ""
    labels = [
        "Mã tin nhắn",
        "Thời gian",
        "Người nhập",
        "Mã SP",
        "Số lượng",
        "Mã phiếu sản xuất",
        "Ghi chú",
        "Link tin nhắn",
    ]
    lines = [
        f"{label}: {values[idx] if idx < len(values) and values[idx] else ''}"
        for idx, label in enumerate(labels)
    ]
    return "\n".join(lines)
