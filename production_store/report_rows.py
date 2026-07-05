"""Bảng QUAN HỆ cho báo cáo thợ (production_report_rows) — 1 dòng / thợ / phiếu.

Song song với blob JSON `bang` trên production_slips (blob vẫn là nguồn cho UI hiện
tại). Bảng này để DASHBOARD sau này tổng hợp theo thợ / sản phẩm / ngày (blob JSON
không query/aggregate được ở SQL). Ghi lại mỗi lần lưu báo cáo (xoá cũ + chèn mới cho
phiếu đó — mỗi lần lưu thay TOÀN BỘ báo cáo). Nằm trong app.db (SHARED_DB_PATH).

Hook: production_store.queries.set_bang gọi replace_report_rows sau khi ghi blob.
"""
from __future__ import annotations

import json
import re

_SCHEMA = """
CREATE TABLE IF NOT EXISTS production_report_rows (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id    INTEGER NOT NULL,          -- phiếu SX (= forum topic id)
    worker_name  TEXT    NOT NULL,          -- tên thợ
    product_code TEXT,                      -- mã SP của phiếu
    report_date  TEXT,                      -- ngày báo cáo gốc (d/m/yyyy)
    report_ymd   TEXT,                      -- chuẩn hoá ISO YYYY-MM-DD (lọc theo ngày/tháng)
    so_gach      REAL DEFAULT 0,
    so_tru       REAL DEFAULT 0,
    so_cay_le    REAL DEFAULT 0,
    so_mam       REAL DEFAULT 0,            -- số mâm (đã tính)
    tong_calc    REAL DEFAULT 0,            -- tổng SP thợ đó (đã tính)
    note         TEXT,
    saved_at     TEXT DEFAULT (datetime('now'))
);
"""
_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_prr_thread  ON production_report_rows(thread_id)",
    "CREATE INDEX IF NOT EXISTS idx_prr_worker  ON production_report_rows(worker_name)",
    "CREATE INDEX IF NOT EXISTS idx_prr_ymd     ON production_report_rows(report_ymd)",
    "CREATE INDEX IF NOT EXISTS idx_prr_product ON production_report_rows(product_code)",
]


def ensure_report_rows_schema(conn) -> None:
    conn.executescript(_SCHEMA)
    for sql in _INDEXES:
        conn.execute(sql)
    conn.commit()


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _parse_ymd(s) -> str | None:
    """"5/7/2026" → "2026-07-05" (best-effort). None nếu không nhận dạng được."""
    if not s:
        return None
    m = re.match(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})", str(s))
    if not m:
        return None
    d, mo, y = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def replace_report_rows(conn, thread_id, bang) -> int:
    """Thay TOÀN BỘ dòng báo cáo của 1 phiếu = nội dung blob `bang`. Trả số dòng ghi."""
    if isinstance(bang, str):
        try:
            bang = json.loads(bang or "{}")
        except Exception:
            return 0
    if not isinstance(bang, dict):
        return 0
    ensure_report_rows_schema(conn)
    product = bang.get("product_code")
    rdate = bang.get("date")
    rymd = _parse_ymd(rdate)
    conn.execute("DELETE FROM production_report_rows WHERE thread_id = ?", (thread_id,))
    n = 0
    for r in bang.get("rows") or []:
        name = (r.get("name") or "").strip()
        if not name:
            continue
        conn.execute(
            """INSERT INTO production_report_rows
               (thread_id, worker_name, product_code, report_date, report_ymd,
                so_gach, so_tru, so_cay_le, so_mam, tong_calc, note)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (thread_id, name, product, rdate, rymd,
             _num(r.get("so_gach")), _num(r.get("so_tru")), _num(r.get("so_cay_le")),
             _num(r.get("so_mam")), _num(r.get("tong_calc")), r.get("note") or ""),
        )
        n += 1
    conn.commit()
    return n


def dashboard(conn, dfrom: str | None = None, dto: str | None = None) -> dict:
    """Tổng hợp cho dashboard: tổng, theo thợ, theo ngày, theo SP. Lọc theo report_ymd
    (YYYY-MM-DD) nếu có dfrom/dto. Chỉ tính dòng có sản lượng (tong_calc > 0)."""
    ensure_report_rows_schema(conn)
    where = "WHERE tong_calc > 0"
    args: list = []
    if dfrom:
        where += " AND report_ymd >= ?"
        args.append(dfrom)
    if dto:
        where += " AND report_ymd <= ?"
        args.append(dto)
    T = "production_report_rows"
    tot = conn.execute(
        f"SELECT COALESCE(SUM(tong_calc),0), COUNT(DISTINCT thread_id), COUNT(DISTINCT worker_name) FROM {T} {where}",
        args).fetchone()
    by_worker = conn.execute(
        f"SELECT worker_name, ROUND(SUM(tong_calc),1), COUNT(DISTINCT thread_id), ROUND(SUM(so_mam),1) "
        f"FROM {T} {where} GROUP BY worker_name ORDER BY SUM(tong_calc) DESC", args).fetchall()
    by_day = conn.execute(
        f"SELECT report_ymd, ROUND(SUM(tong_calc),1), COUNT(DISTINCT thread_id) "
        f"FROM {T} {where} AND report_ymd IS NOT NULL GROUP BY report_ymd ORDER BY report_ymd DESC LIMIT 60",
        args).fetchall()
    by_product = conn.execute(
        f"SELECT product_code, ROUND(SUM(tong_calc),1), COUNT(DISTINCT thread_id) "
        f"FROM {T} {where} GROUP BY product_code ORDER BY SUM(tong_calc) DESC", args).fetchall()
    return {
        "totals": {"tong": tot[0] or 0, "phieu": tot[1] or 0, "tho": tot[2] or 0},
        "by_worker": [{"name": r[0], "tong": r[1] or 0, "phieu": r[2], "mam": r[3] or 0} for r in by_worker],
        "by_day": [{"ymd": r[0], "tong": r[1] or 0, "phieu": r[2]} for r in by_day],
        "by_product": [{"code": r[0] or "?", "tong": r[1] or 0, "phieu": r[2]} for r in by_product],
    }


def backfill_report_rows(conn) -> int:
    """Nạp lại toàn bộ từ blob `bang` hiện có (chạy 1 lần khi thêm bảng). Trả số phiếu."""
    ensure_report_rows_schema(conn)
    slips = conn.execute(
        "SELECT thread_id, bang FROM production_slips WHERE bang IS NOT NULL AND bang != ''"
    ).fetchall()
    count = 0
    for row in slips:
        try:
            replace_report_rows(conn, row[0], row[1])
            count += 1
        except Exception:
            pass
    return count
