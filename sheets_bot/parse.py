"""sheets_bot.parse — PURE functions (no network / no IO).

Faithful port of the pure helpers from bot.js. Everything here is unit-testable
offline: quoted-row parsing, date parsing, gviz parsing, number/date helpers and
HTML building.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Header schema (order matters — mirrors bot.js HEADERS exactly)
# ---------------------------------------------------------------------------
HEADERS = [
    "Tên",
    "Số gạch",
    "Số trừ",
    "Số cây lẻ",
    "Ghi chú",
    "Tổng số SP",
    "Số giờ TL",
    "Lương 1 SP",
    "Lương 1 giờ TL",
    "Tổng lương SP",
    "Tổng lương TL",
    "Phụ cấp",
    "Tổng lương phiếu",
    "Sản phẩm",
    "Ngày",
    "STT",
    "Số chảo",
    "Số mâm",
    "Giờ vào",
    "Giờ ra",
    "Lương trên 1 giờ",
    "Link",
    "Cập nhật lần cuối",
]
DATE_HEADER = "Ngày"
NEW_COLUMNS_BEFORE_LINK = ["Số mâm", "Giờ vào", "Giờ ra", "Lương trên 1 giờ"]
MANAGED_HEADER_MARKERS = [
    "Tên",
    "Số gạch",
    "Tổng số SP",
    "Sản phẩm",
    "Ngày",
    "STT",
    "Link",
    "Cập nhật lần cuối",
]

HIDDEN_EXPORT_HEADERS = {
    "Lương 1 SP",
    "Lương 1 giờ TL",
    "Tổng lương SP",
    "Tổng lương TL",
    "Phụ cấp",
    "Tổng lương phiếu",
    "Lương trên 1 giờ",
}

# Array formulas re-applied on each managed sheet (verbatim from bot.js).
ARRAY_FORMULAS = [
    {
        "range": "H1",
        "formula": '={"Lương 1 SP";ARRAYFORMULA(IF(N2:N="";"";VLOOKUP(N2:N;\'Sản phẩm\'!A2:D;4;FALSE)))}',
    },
    {
        "range": "I1",
        "formula": '={"Lương 1 giờ TL";ARRAYFORMULA(IF(A2:A="";"";VLOOKUP(A2:A;\'Nhân viên\'!A2:B;2;FALSE)))}',
    },
    {
        "range": "J1",
        "formula": '={"Tổng lương SP";ARRAYFORMULA(IF(A2:A = ""; ""; F2:F * H2:H))}',
    },
    {
        "range": "K1",
        "formula": '={"Tổng lương TL";ARRAYFORMULA(IF(A2:A = ""; ""; G2:G * I2:I))}',
    },
    {
        "range": "M1",
        "formula": '={"Tổng lương phiếu";ARRAYFORMULA(IF(A2:A = ""; ""; J2:J+K2:K+L2:L))}',
    },
    {
        "range": "U1",
        "formula": '={"Lương trên 1 giờ";ARRAYFORMULA(IF(A2:A = ""; ""; IFERROR(IF((VALUE(T2:T)-VALUE(S2:S))<=0; ""; M2:M/((VALUE(T2:T)-VALUE(S2:S))*IF((VALUE(T2:T)-VALUE(S2:S))<1;24;1))); "")))}',
    },
]


# ---------------------------------------------------------------------------
# Column helpers
# ---------------------------------------------------------------------------
def end_column_letter() -> str:
    return chr(ord("A") + len(HEADERS) - 1)


def column_letter(idx: int) -> str:
    return chr(ord("A") + idx)


def a1(sheet_name: str, rng: str) -> str:
    escaped = (sheet_name or "").replace("'", "''")
    return f"'{escaped}'!{rng}"


# ---------------------------------------------------------------------------
# Header helpers
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Date / sheet-name helpers
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Bangkok time helpers (Asia/Bangkok, +07:00)
# ---------------------------------------------------------------------------
def format_date_ddmmyyyy(dt: datetime) -> str:
    return f"{dt.day:02d}/{dt.month:02d}/{dt.year:04d}"


def format_iso_with_offset(dt: datetime, offset: str = "+07:00") -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + offset


# ---------------------------------------------------------------------------
# Payload parsing
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# GViz parsing
# ---------------------------------------------------------------------------
def parse_gviz_response(body: str) -> dict:
    m = re.search(r"setResponse\((.*)\);?$", body, re.S)
    if not m:
        raise ValueError("Invalid GViz response.")
    payload = json.loads(m.group(1))
    status = payload.get("status")
    if status and status != "ok":
        errors = payload.get("errors") or []
        msg = errors[0].get("message") if errors else None
        raise ValueError(msg or "GViz query failed.")
    return payload


def get_gviz_cell_value(cell: Any) -> Any:
    if not cell:
        return None
    v = cell.get("v")
    if v is not None:
        return v
    f = cell.get("f")
    if f is not None:
        return f
    return None


# ---------------------------------------------------------------------------
# Formula / URL helpers
# ---------------------------------------------------------------------------
def escape_formula_string(value: Any) -> str:
    return str(value if value is not None else "").replace('"', '""')


def build_sheet_row_url(spreadsheet_id: str, gid: Any, row_number: Any) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={gid}&range=A{row_number}"


def build_hyperlink_formula(url: str, label: str) -> str:
    return f'=HYPERLINK("{escape_formula_string(url)}";"{escape_formula_string(label)}")'


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# HTML export builder (faithful port of buildHtml)
# ---------------------------------------------------------------------------
def escape_html(s: Any) -> str:
    s = "" if s is None else str(s)
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _is_finite_number(x) -> bool:
    return isinstance(x, (int, float)) and x == x and x not in (float("inf"), float("-inf"))


def build_html(sheet_name: str, rows: list) -> str:
    safe_name = escape_html(sheet_name)
    header = rows[0] if rows else []
    body_rows = rows[1:] if rows else []

    def find_idx(name):
        for i, h in enumerate(header):
            if ("" if h is None else str(h)).strip() == name:
                return i
        return -1

    stt_idx = find_idx("STT")
    product_idx = find_idx("Sản phẩm")
    total_sp_idx = find_idx("Tổng số SP")

    head_cells = "".join(f"<th>{escape_html(c or '')}</th>" for c in header)

    groups = []
    group_map = {}

    for row in body_rows:
        stt_raw = ""
        if stt_idx >= 0 and stt_idx < len(row):
            stt_raw = ("" if row[stt_idx] is None else str(row[stt_idx])).strip()
        key = stt_raw or "—"
        group = group_map.get(key)
        if group is None:
            group = {"stt": stt_raw, "rows": [], "products": [], "products_set": set(), "totalSp": 0.0}
            group_map[key] = group
            groups.append(group)
        if product_idx >= 0 and product_idx < len(row):
            p = ("" if row[product_idx] is None else str(row[product_idx])).strip()
            if p and p not in group["products_set"]:
                group["products_set"].add(p)
                group["products"].append(p)
        if total_sp_idx >= 0 and total_sp_idx < len(row):
            raw = ("0" if row[total_sp_idx] is None else str(row[total_sp_idx])).replace(",", ".")
            try:
                v = float(raw)
                group["totalSp"] += v
            except ValueError:
                pass
        group["rows"].append(row)

    def sort_key(g):
        stt = g["stt"]
        try:
            num = float(stt)
            is_num = _is_finite_number(num)
        except (ValueError, TypeError):
            num, is_num = None, False
        return (0, num) if is_num else (1, stt or "")

    groups.sort(key=sort_key)

    def render_group(g):
        prod_list = ", ".join(escape_html(p) for p in g["products"]) if g["products"] else "—"
        total = g["totalSp"]
        total_display = total if _is_finite_number(total) else ""
        # JS Number formatting: integers render without decimals, e.g. 5 not 5.0
        if isinstance(total_display, float) and total_display.is_integer():
            total_display = int(total_display)
        rows_html = "".join(
            "<tr>" + "".join(f"<td>{escape_html(c or '')}</td>" for c in r) + "</tr>"
            for r in g["rows"]
        )
        return f"""
    <div class="group">
      <div class="group-meta">
        <span><strong>STT:</strong> {escape_html(g['stt'] or '—')}</span>
        <span><strong>Sản phẩm:</strong> {prod_list}</span>
        <span><strong>Tổng số SP:</strong> {escape_html(str(total_display))}</span>
      </div>
      <table>
        <thead><tr>{head_cells}</tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>"""

    sections = [render_group(g) for g in groups]

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>{safe_name}</title>
  <style>
    body {{ font-family: Arial, sans-serif; padding: 12px; }}
    h1 {{ font-size: 16px; margin-bottom: 12px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 12px; margin-top: 6px; }}
    th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; }}
    th {{ background: #f5f5f5; }}
    .group {{ margin-bottom: 16px; }}
    .group-meta {{ display: flex; gap: 12px; font-size: 13px; }}
  </style>
</head>
<body>
  <h1>{safe_name}</h1>
  {chr(10).join(sections)}
</body>
</html>"""
