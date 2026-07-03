"""Pure parsing + compute for the production worker báo cáo (CSV/semicolon).

No IO. Backs BOTH the Telegram handler (command_handlers/production_commands.py)
and the webapp endpoint (server_app/production_routes.py) so the two never drift.

Real-world data is semicolon-delimited, one line per worker, columns:
    0 name | 1 số gạch | 2 số trừ | 3 số cây lẻ | 4 note(nghỉ/vít/vô kẹo/Q.kẹo)
    5 tổng sp(sheet) | ... | 13 mã SP | 14 date | 15 số cây 1 mâm | 16 ? | 17 số mâm
    18 giờ bắt đầu | 19 giờ kết thúc
Also tolerates the older comma/tab formats with a "thợ" header (no note column
→ tổng at index 4). Decimals may use comma (``3,5``).
"""
from __future__ import annotations

# Column indices in the semicolon layout.
_C_NAME = 0
_C_GACH = 1
_C_TRU = 2
_C_LE = 3
_C_NOTE = 4
_C_TONG_SEMI = 5   # tổng sp when a note column is present (semicolon layout)
_C_TONG_COMMA = 4  # tổng sp in the legacy comma/tab layout (no note column)
_C_CODE = 13
_C_DATE = 14
_C_SOMAM = 17  # số mâm đã tính sẵn trong sheet (nguồn chuẩn cho tổng SP)
_C_START = 18
_C_END = 19

_NOTE_WORDS = {"nghỉ", "nghi", "vít", "vit", "vô kẹo", "vo keo", "q.kẹo", "q.keo", "qkẹo"}


def _num(val) -> float:
    """Parse a cell to float; comma decimal → dot; blanks/garbage → 0.0."""
    if val is None:
        return 0.0
    s = str(val).strip().strip('"').strip("'").strip()
    if not s:
        return 0.0
    s = s.replace(".", "").replace(",", ".") if s.count(",") == 1 and "." in s else s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _is_num_cell(val: str) -> bool:
    s = str(val).strip().strip('"')
    if not s:
        return False
    try:
        float(s.replace(",", "."))
        return True
    except ValueError:
        return False


def _pick_delimiter(first_line: str) -> str:
    if ";" in first_line:
        return ";"
    if "\t" in first_line:
        return "\t"
    return ","


def _split(line: str, delim: str) -> list[str]:
    # simple split is fine for ; and \t; comma layout has no quoted commas in practice
    return [c.strip().strip('"').strip("'").strip() for c in line.split(delim)]


def looks_like_report(text: str) -> bool:
    """True when text looks like a pasted worker báo cáo (multi-column, ≥2 rows)."""
    if not text:
        return False
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if len(lines) < 2:
        return False
    delim = _pick_delimiter(lines[0])
    wide = sum(1 for ln in lines if len(ln.split(delim)) >= 5)
    return wide >= 2


def parse_report(text: str) -> dict:
    """Parse a báo cáo into raw rows + extracted product_code/date/time. Pure.

    Returns ``{product_code, date, start, end, rows: [{name, so_gach, so_tru,
    so_cay_le, note, tong_sheet}]}``. Does NOT apply the yield formula — call
    compute_report() with the product's số cây 1 mâm for totals.
    """
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if not lines:
        return {"product_code": None, "date": None, "start": None, "end": None, "rows": []}
    delim = _pick_delimiter(lines[0])
    has_note_col = delim == ";"

    product_code = None
    date = start = end = None
    rows: list[dict] = []
    for idx, raw in enumerate(lines):
        cells = _split(raw, delim)
        # skip a header row (first line, non-numeric qty columns)
        if idx == 0 and (
            "thợ" in (cells[0] or "").lower()
            or (len(cells) > 1 and cells[1] and not _is_num_cell(cells[1]) and not _is_num_cell(cells[2] if len(cells) > 2 else ""))
        ):
            continue
        if len(cells) < 4:
            continue
        note = cells[_C_NOTE] if has_note_col and len(cells) > _C_NOTE else ""
        tong_idx = _C_TONG_SEMI if has_note_col else _C_TONG_COMMA
        rows.append({
            "name": cells[_C_NAME],
            "so_gach": _num(cells[_C_GACH]),
            "so_tru": _num(cells[_C_TRU]),
            "so_cay_le": _num(cells[_C_LE]),
            "note": note,
            "tong_sheet": _num(cells[tong_idx]) if len(cells) > tong_idx else 0.0,
            # số mâm sheet đã tính (None nếu dòng không có cột 17) — nguồn chuẩn
            "so_mam_sheet": _num(cells[_C_SOMAM]) if len(cells) > _C_SOMAM else None,
        })
        if product_code is None and len(cells) > _C_CODE and cells[_C_CODE]:
            product_code = cells[_C_CODE].upper()
        if date is None and len(cells) > _C_DATE and cells[_C_DATE]:
            date = cells[_C_DATE]
        if start is None and len(cells) > _C_START and cells[_C_START]:
            start = cells[_C_START]
        if end is None and len(cells) > _C_END and cells[_C_END]:
            end = cells[_C_END]
    return {"product_code": product_code, "date": date, "start": start, "end": end, "rows": rows}


def _round2(x: float) -> float:
    return round(x * 100) / 100


def compute_report(parsed: dict, so_cay_1_mam: float) -> dict:
    """Apply the yield formula to parsed rows.

    total = số_cây_1_mâm × số_mâm + lẻ
    Số mâm ưu tiên lấy từ cột 17 của sheet (đã tính sẵn — đúng cho cả kiểu nhập
    trực tiếp số mâm như KDDT lẫn kiểu nhập gạch). Nếu dòng không có cột 17 thì
    suy ra từ gạch: max(gạch×5 − trừ − (1 if lẻ>0 else 0), 0).
    Khi số cây 1 mâm chưa biết (0/None) → dùng cột tổng của sheet.
    Note-rows (nghỉ/vít/…) không có số liệu → tự nhiên bằng 0.
    """
    scm = float(so_cay_1_mam or 0)
    out_rows = []
    grand_total = 0.0
    for row in parsed.get("rows", []):
        gach, tru, le = row["so_gach"], row["so_tru"], row["so_cay_le"]
        somam_sheet = row.get("so_mam_sheet")
        if scm > 0:
            if somam_sheet is not None:
                so_mam = somam_sheet
            else:
                so_mam = max(gach * 5 - tru - (1 if le > 0 else 0), 0)
            total = scm * so_mam + le
        else:
            so_mam = somam_sheet or 0.0
            total = row.get("tong_sheet", 0.0)
        total = _round2(total)
        if total > 0:
            grand_total += total
        out_rows.append({**row, "so_mam": so_mam, "tong_calc": total})
    return {
        "product_code": parsed.get("product_code"),
        "date": parsed.get("date"),
        "start": parsed.get("start"),
        "end": parsed.get("end"),
        "so_cay_1_mam": scm,
        "rows": out_rows,
        "grand_total": _round2(grand_total),
    }
