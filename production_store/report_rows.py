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
    worker_id    INTEGER,                   -- → production_workers.id (danh tính bất biến)
    worker_name  TEXT    NOT NULL,          -- tên thợ snapshot (hiển thị fallback)
    product_id   INTEGER,                   -- → products.id (danh tính bất biến)
    product_code TEXT,                      -- mã SP snapshot (hiển thị fallback)
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
    "CREATE INDEX IF NOT EXISTS idx_prr_pid     ON production_report_rows(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_prr_wid     ON production_report_rows(worker_id)",
]


def ensure_report_rows_schema(conn) -> None:
    conn.executescript(_SCHEMA)
    # reads join production_workers (tên thợ sống) → đảm bảo bảng tồn tại
    try:
        from worker_store import ensure_table as _ensure_workers
        _ensure_workers(conn)
    except Exception:  # noqa: BLE001
        pass
    cols = {r[1] for r in conn.execute("PRAGMA table_info(production_report_rows)").fetchall()}
    if "product_id" not in cols:  # migrate DB cũ + backfill theo mã snapshot
        conn.execute("ALTER TABLE production_report_rows ADD COLUMN product_id INTEGER")
        conn.execute(
            "UPDATE production_report_rows SET product_id = "
            "(SELECT p.id FROM products p WHERE p.code = UPPER(TRIM(COALESCE(production_report_rows.product_code,''))))"
        )
    if "worker_id" not in cols:  # migrate DB cũ + backfill theo tên (production_workers)
        conn.execute("ALTER TABLE production_report_rows ADD COLUMN worker_id INTEGER")
        try:
            conn.execute(
                "UPDATE production_report_rows SET worker_id = "
                "(SELECT w.id FROM production_workers w WHERE w.name = TRIM(production_report_rows.worker_name) COLLATE NOCASE)"
            )
        except Exception:  # noqa: BLE001 — production_workers chưa tạo (DB test)
            pass
    if "so_gio" not in cols:  # số giờ làm (SP tính lương theo giờ) — NULL = không nhập
        conn.execute("ALTER TABLE production_report_rows ADD COLUMN so_gio REAL")
    for sql in _INDEXES:
        conn.execute(sql)
    conn.commit()


def _worker_id_map(conn) -> dict[str, int]:
    """{tên thường: worker_id} để resolve khi ghi báo cáo. Rỗng nếu chưa có bảng."""
    try:
        return {
            str(r[1]).strip().lower(): int(r[0])
            for r in conn.execute("SELECT id, name FROM production_workers").fetchall()
        }
    except Exception:  # noqa: BLE001
        return {}


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
    # resolve danh tính SP (nhận cả mã cũ) + chuẩn hoá mã snapshot về hiện hành
    pid = None
    if product:
        from product_store import resolve_code
        prod = resolve_code(conn, product)
        if prod:
            pid, product = prod["id"], prod["code"]
    rdate = bang.get("date")
    rymd = _parse_ymd(rdate)
    conn.execute("DELETE FROM production_report_rows WHERE thread_id = ?", (thread_id,))
    wmap = _worker_id_map(conn)
    n = 0
    for r in bang.get("rows") or []:
        name = (r.get("name") or "").strip()
        if not name:
            continue
        gio = r.get("so_gio")
        conn.execute(
            """INSERT INTO production_report_rows
               (thread_id, worker_id, worker_name, product_id, product_code, report_date, report_ymd,
                so_gach, so_tru, so_cay_le, so_mam, tong_calc, note, so_gio)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (thread_id, wmap.get(name.lower()), name, pid, product, rdate, rymd,
             _num(r.get("so_gach")), _num(r.get("so_tru")), _num(r.get("so_cay_le")),
             _num(r.get("so_mam")), _num(r.get("tong_calc")), r.get("note") or "",
             None if gio is None else _num(gio)),
        )
        n += 1
    conn.commit()
    return n


def report_summaries(conn, thread_ids) -> dict:
    """Tóm tắt báo cáo thợ cho 1 trang phiếu: {thread_id: {"total", "workers":
    [{"name","tong"}], "notes": [{"name","note"}]}} (workers sắp tổng giảm dần;
    notes = thợ KHÔNG có sản lượng nhưng có ghi chú, vd 'Kim vít'). Cho card + realtime."""
    ids = [int(t) for t in thread_ids if t is not None]
    if not ids:
        return {}
    ensure_report_rows_schema(conn)
    q = ",".join("?" * len(ids))
    # tên hiển thị = tên HIỆN HÀNH của thợ (join worker_id), fallback snapshot
    rows = conn.execute(
        f"SELECT t.thread_id, COALESCE(w.name, t.worker_name), ROUND(SUM(t.tong_calc),1) "
        f"FROM production_report_rows t LEFT JOIN production_workers w ON w.id = t.worker_id "
        f"WHERE t.thread_id IN ({q}) AND t.tong_calc > 0 "
        f"GROUP BY t.thread_id, COALESCE(w.name, t.worker_name) "
        f"ORDER BY t.thread_id, SUM(t.tong_calc) DESC", ids).fetchall()
    out: dict = {}
    for tid, name, tong in rows:
        d = out.setdefault(tid, {"total": 0.0, "workers": [], "notes": []})
        d["workers"].append({"name": name, "tong": tong or 0})
        d["total"] = round(d["total"] + (tong or 0), 1)
    note_rows = conn.execute(
        f"SELECT t.thread_id, COALESCE(w.name, t.worker_name), TRIM(t.note) "
        f"FROM production_report_rows t LEFT JOIN production_workers w ON w.id = t.worker_id "
        f"WHERE t.thread_id IN ({q}) AND COALESCE(t.tong_calc, 0) <= 0 "
        f"AND TRIM(COALESCE(t.note, '')) != '' ORDER BY t.thread_id, COALESCE(w.name, t.worker_name)", ids).fetchall()
    for tid, name, note in note_rows:
        d = out.setdefault(tid, {"total": 0.0, "workers": [], "notes": []})
        d["notes"].append({"name": name, "note": note})
    return out


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
        f"SELECT COALESCE(w.name, t.worker_name), ROUND(SUM(t.tong_calc),1), "
        f"COUNT(DISTINCT t.thread_id), ROUND(SUM(t.so_mam),1) "
        f"FROM {T} t LEFT JOIN production_workers w ON w.id = t.worker_id "
        f"{where.replace('tong_calc', 't.tong_calc').replace('report_ymd', 't.report_ymd')} "
        f"GROUP BY COALESCE(w.name, t.worker_name) ORDER BY SUM(t.tong_calc) DESC", args).fetchall()
    by_day = conn.execute(
        f"SELECT report_ymd, ROUND(SUM(tong_calc),1), COUNT(DISTINCT thread_id) "
        f"FROM {T} {where} AND report_ymd IS NOT NULL GROUP BY report_ymd ORDER BY report_ymd DESC LIMIT 60",
        args).fetchall()
    by_product = conn.execute(
        f"SELECT COALESCE(pr.code, t.product_code), ROUND(SUM(t.tong_calc),1), COUNT(DISTINCT t.thread_id) "
        f"FROM {T} t LEFT JOIN products pr ON pr.id = t.product_id "
        f"{where.replace('tong_calc', 't.tong_calc').replace('report_ymd', 't.report_ymd')} "
        f"GROUP BY COALESCE(pr.code, t.product_code) ORDER BY SUM(t.tong_calc) DESC", args).fetchall()
    return {
        "totals": {"tong": tot[0] or 0, "phieu": tot[1] or 0, "tho": tot[2] or 0},
        "by_worker": [{"name": r[0], "tong": r[1] or 0, "phieu": r[2], "mam": r[3] or 0} for r in by_worker],
        "by_day": [{"ymd": r[0], "tong": r[1] or 0, "phieu": r[2]} for r in by_day],
        "by_product": [{"code": r[0] or "?", "tong": r[1] or 0, "phieu": r[2]} for r in by_product],
    }


def worker_detail(conn, name: str, dfrom: str | None = None, dto: str | None = None) -> dict:
    """Chi tiết 1 thợ: mỗi phiếu thợ CÓ MẶT (kể cả làm 0 SP), SP gì, bao nhiêu. Sắp ngày
    mới→cũ. Khớp theo DANH TÍNH (worker_id) khi tên có trong danh sách thợ — dòng cổ
    mang tên cũ vẫn ra; tên lạ fallback so tên snapshot."""
    ensure_report_rows_schema(conn)
    wid = None
    try:
        r = conn.execute(
            "SELECT id FROM production_workers WHERE name = TRIM(?) COLLATE NOCASE", (name,)
        ).fetchone()
        wid = int(r[0]) if r else None
    except Exception:  # noqa: BLE001
        pass
    if wid is not None:
        where = "WHERE (t.worker_id = ? OR (t.worker_id IS NULL AND t.worker_name = TRIM(?) COLLATE NOCASE))"
        args: list = [wid, name]
    else:
        where = "WHERE t.worker_name = TRIM(?) COLLATE NOCASE"
        args = [name]
    if dfrom:
        where += " AND t.report_ymd >= ?"
        args.append(dfrom)
    if dto:
        where += " AND t.report_ymd <= ?"
        args.append(dto)
    rows = conn.execute(
        f"SELECT t.thread_id, COALESCE(pr.code, t.product_code), t.report_date, t.report_ymd, "
        f"t.so_gach, t.so_tru, t.so_cay_le, t.so_mam, t.tong_calc, t.note, t.so_gio "
        f"FROM production_report_rows t LEFT JOIN products pr ON pr.id = t.product_id "
        f"{where} ORDER BY t.report_ymd DESC, t.thread_id DESC", args).fetchall()
    total = round(sum(r[8] or 0 for r in rows), 1)
    total_mam = round(sum(r[7] or 0 for r in rows), 1)
    phieu = len({r[0] for r in rows if (r[8] or 0) > 0})
    return {
        "name": name, "total": total, "total_mam": total_mam, "phieu": phieu,
        "rows": [{
            "thread_id": r[0], "product_code": r[1] or "?", "date": r[2], "ymd": r[3],
            "so_gach": r[4] or 0, "so_tru": r[5] or 0, "so_cay_le": r[6] or 0,
            "so_mam": r[7] or 0, "tong_calc": r[8] or 0, "note": r[9] or "",
            "so_gio": r[10],   # None = không nhập giờ
        } for r in rows],
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
