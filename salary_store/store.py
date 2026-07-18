"""Lương THÁNG: phụ cấp/thưởng theo tháng + ứng lương (nhiều lần) — app.db.

2 bảng:
- salary_month(ym, worker_id, phu_cap, thuong, note): 1 dòng/(tháng, thợ) — phụ cấp +
  thưởng văn phòng gán theo THÁNG (khác phụ cấp per-phiếu SX ở production_allowances).
- salary_advances(id, worker_id, ym, amount, adv_date, note, ...): ỨNG lương NHIỀU lần/
  tháng, cộng dồn trừ vào lương.

compute_month_payroll gộp lương SP (production_store.report_slips.compute_range_report
theo khoảng tháng) + phụ cấp + thưởng − ứng = thực lãnh cho MỌI thợ. Thợ 'time' (lương
thời gian) → lương = 0 (chờ chấm công). Nối: utils.db, worker_store, production_store.
"""
from __future__ import annotations

import calendar

from utils.db import transaction

_SCHEMA = """
CREATE TABLE IF NOT EXISTS salary_month (
    ym          TEXT    NOT NULL,          -- 'YYYY-MM'
    worker_id   INTEGER NOT NULL,
    phu_cap     REAL    NOT NULL DEFAULT 0,
    thuong      REAL    NOT NULL DEFAULT 0,
    note        TEXT    DEFAULT '',
    updated_at  TEXT    DEFAULT (datetime('now', '+7 hours')),
    updated_by  TEXT    DEFAULT '',
    UNIQUE(ym, worker_id)
);
CREATE TABLE IF NOT EXISTS salary_advances (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_id   INTEGER NOT NULL,
    ym          TEXT    NOT NULL,          -- tháng tính ứng vào 'YYYY-MM'
    amount      REAL    NOT NULL DEFAULT 0,
    adv_date    TEXT    DEFAULT '',         -- ngày ứng 'YYYY-MM-DD'
    note        TEXT    DEFAULT '',
    created_by  TEXT    DEFAULT '',
    created_at  TEXT    DEFAULT (datetime('now', '+7 hours'))
);
CREATE TABLE IF NOT EXISTS salary_allowances (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_id   INTEGER NOT NULL,
    ym          TEXT    NOT NULL,          -- tháng tính phụ cấp vào 'YYYY-MM'
    amount      REAL    NOT NULL DEFAULT 0,
    note        TEXT    DEFAULT '',         -- nhãn khoản phụ cấp (ăn trưa, xăng xe…)
    created_by  TEXT    DEFAULT '',
    created_at  TEXT    DEFAULT (datetime('now', '+7 hours'))
);
"""
_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_salary_month_ym ON salary_month(ym)",
    "CREATE INDEX IF NOT EXISTS idx_salary_adv ON salary_advances(ym, worker_id)",
    "CREATE INDEX IF NOT EXISTS idx_salary_allow ON salary_allowances(ym, worker_id)",
]


def ensure_schema(conn) -> None:
    conn.executescript(_SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(salary_month)").fetchall()}
    if "weekly" not in cols:   # nhận lương tuần THEO THÁNG (riêng bảng lương, không phải hồ sơ thợ)
        conn.execute("ALTER TABLE salary_month ADD COLUMN weekly INTEGER DEFAULT 0")
    for sql in _INDEXES:
        conn.execute(sql)
    conn.commit()


def month_range(ym: str) -> tuple[str, str]:
    """'2026-07' → ('2026-07-01', '2026-07-31')."""
    y, m = (int(x) for x in ym.split("-")[:2])
    last = calendar.monthrange(y, m)[1]
    return f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-{last:02d}"


# ── Phụ cấp / thưởng theo tháng ─────────────────────────────────────────────────

def get_month_adjust(conn, ym: str) -> dict:
    """{worker_id: {'thuong', 'note', 'weekly'}} của 1 tháng. (Phụ cấp giờ là NHIỀU
    KHOẢN ở salary_allowances — xem allowance_totals.)"""
    ensure_schema(conn)
    rows = conn.execute(
        "SELECT worker_id, thuong, note, weekly FROM salary_month WHERE ym = ?", (ym,)
    ).fetchall()
    return {r["worker_id"]: {"thuong": float(r["thuong"] or 0),
                             "note": r["note"] or "", "weekly": bool(r["weekly"])} for r in rows}


def set_month_adjust(conn, ym: str, worker_id: int, *, thuong=None,
                     note=None, weekly=None, by: str = "") -> None:
    """Cập nhật thưởng/ghi chú/nhận-lương-tuần 1 (tháng, thợ). Field None = giữ nguyên.
    weekly = nhận lương tuần THEO THÁNG (riêng bảng lương, không phải hồ sơ thợ). Phụ cấp
    KHÔNG ở đây nữa — dùng add_allowance (nhiều khoản)."""
    ensure_schema(conn)
    with transaction(conn):
        cur = conn.execute(
            "SELECT thuong, note, weekly FROM salary_month WHERE ym = ? AND worker_id = ?",
            (ym, worker_id),
        ).fetchone()
        th = float(cur["thuong"] or 0) if cur else 0.0
        nt = (cur["note"] or "") if cur else ""
        wk = int(cur["weekly"] or 0) if cur else 0
        if thuong is not None:
            th = max(0.0, float(thuong))
        if note is not None:
            nt = str(note)
        if weekly is not None:
            wk = 1 if weekly else 0
        conn.execute(
            "INSERT INTO salary_month (ym, worker_id, thuong, note, weekly, updated_at, updated_by) "
            "VALUES (?, ?, ?, ?, ?, datetime('now','+7 hours'), ?) "
            "ON CONFLICT(ym, worker_id) DO UPDATE SET thuong=excluded.thuong, "
            "note=excluded.note, weekly=excluded.weekly, updated_at=excluded.updated_at, updated_by=excluded.updated_by",
            (ym, worker_id, th, nt, wk, by or ""),
        )


# ── Ứng lương (nhiều lần / tháng) ────────────────────────────────────────────────

def list_advances(conn, ym: str, worker_id: int | None = None) -> list[dict]:
    ensure_schema(conn)
    q = "SELECT id, worker_id, ym, amount, adv_date, note, created_by, created_at FROM salary_advances WHERE ym = ?"
    args: list = [ym]
    if worker_id is not None:
        q += " AND worker_id = ?"
        args.append(worker_id)
    q += " ORDER BY adv_date ASC, id ASC"
    return [{"id": r["id"], "worker_id": r["worker_id"], "ym": r["ym"], "amount": float(r["amount"] or 0),
             "adv_date": r["adv_date"] or "", "note": r["note"] or "", "created_by": r["created_by"] or "",
             "created_at": r["created_at"] or ""} for r in conn.execute(q, args).fetchall()]


def advance_totals(conn, ym: str) -> dict:
    """{worker_id: (tổng ứng, số lần)} của 1 tháng."""
    ensure_schema(conn)
    rows = conn.execute(
        "SELECT worker_id, COALESCE(SUM(amount),0) AS s, COUNT(*) AS c FROM salary_advances "
        "WHERE ym = ? GROUP BY worker_id", (ym,)
    ).fetchall()
    return {r["worker_id"]: (float(r["s"] or 0), int(r["c"])) for r in rows}


def add_advance(conn, worker_id: int, ym: str, amount: float, adv_date: str = "",
                note: str = "", by: str = "") -> dict:
    ensure_schema(conn)
    amt = float(amount or 0)
    if amt <= 0:
        raise ValueError("Số tiền ứng phải > 0")
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO salary_advances (worker_id, ym, amount, adv_date, note, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (worker_id, ym, amt, (adv_date or "").strip(), (note or "").strip(), by or ""),
        )
        aid = cur.lastrowid
    return {"id": aid, "worker_id": worker_id, "ym": ym, "amount": amt,
            "adv_date": (adv_date or "").strip(), "note": (note or "").strip()}


def delete_advance(conn, advance_id: int) -> bool:
    ensure_schema(conn)
    with transaction(conn):
        cur = conn.execute("DELETE FROM salary_advances WHERE id = ?", (advance_id,))
        return cur.rowcount > 0


# ── Phụ cấp (NHIỀU KHOẢN / tháng, giống ứng lương) ──────────────────────────────

def list_allowances(conn, ym: str, worker_id: int | None = None) -> list[dict]:
    ensure_schema(conn)
    q = "SELECT id, worker_id, ym, amount, note, created_by, created_at FROM salary_allowances WHERE ym = ?"
    args: list = [ym]
    if worker_id is not None:
        q += " AND worker_id = ?"
        args.append(worker_id)
    q += " ORDER BY id ASC"
    return [{"id": r["id"], "worker_id": r["worker_id"], "ym": r["ym"], "amount": float(r["amount"] or 0),
             "note": r["note"] or "", "created_by": r["created_by"] or "", "created_at": r["created_at"] or ""}
            for r in conn.execute(q, args).fetchall()]


def allowance_totals(conn, ym: str) -> dict:
    """{worker_id: (tổng phụ cấp, số khoản)} của 1 tháng."""
    ensure_schema(conn)
    rows = conn.execute(
        "SELECT worker_id, COALESCE(SUM(amount),0) AS s, COUNT(*) AS c FROM salary_allowances "
        "WHERE ym = ? GROUP BY worker_id", (ym,)
    ).fetchall()
    return {r["worker_id"]: (float(r["s"] or 0), int(r["c"])) for r in rows}


def add_allowance(conn, worker_id: int, ym: str, amount: float, note: str = "", by: str = "") -> dict:
    ensure_schema(conn)
    amt = float(amount or 0)
    if amt <= 0:
        raise ValueError("Số tiền phụ cấp phải > 0")
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO salary_allowances (worker_id, ym, amount, note, created_by) VALUES (?, ?, ?, ?, ?)",
            (worker_id, ym, amt, (note or "").strip(), by or ""),
        )
        aid = cur.lastrowid
    return {"id": aid, "worker_id": worker_id, "ym": ym, "amount": amt, "note": (note or "").strip()}


def delete_allowance(conn, allowance_id: int) -> bool:
    ensure_schema(conn)
    with transaction(conn):
        cur = conn.execute("DELETE FROM salary_allowances WHERE id = ?", (allowance_id,))
        return cur.rowcount > 0


# ── Bảng lương tháng (tính live) ─────────────────────────────────────────────────

def compute_month_payroll(conn, ym: str) -> dict:
    """Bảng lương 1 tháng cho MỌI thợ: lương (SP tự tính / thời gian = 0) + phụ cấp +
    thưởng − ứng = thực lãnh. Trả {ym, workers:[...], totals:{...}}."""
    from worker_store import list_workers
    from production_store.report_slips import compute_range_report

    ensure_schema(conn)
    workers = list_workers(conn)
    mstart, mend = month_range(ym)
    product_ids = [w["id"] for w in workers if (w.get("wage_type") or "product") == "product"]
    wage_by_name: dict = {}
    if product_ids:
        rep = compute_range_report(conn, mstart, mend, worker_ids=product_ids)
        for w in rep["workers"]:
            wage_by_name[(w.get("name") or "").strip().casefold()] = float(w.get("money") or 0)
    adjust = get_month_adjust(conn, ym)
    adv = advance_totals(conn, ym)
    allow = allowance_totals(conn, ym)   # phụ cấp NHIỀU KHOẢN

    out = []
    tot = {"luong": 0.0, "phu_cap": 0.0, "thuong": 0.0, "ung": 0.0, "thuc_lanh": 0.0}
    for w in workers:
        wid, wt = w["id"], (w.get("wage_type") or "product")
        luong = wage_by_name.get(w["name"].strip().casefold(), 0.0) if wt == "product" else 0.0
        a = adjust.get(wid, {})
        thuong, note = a.get("thuong", 0.0), a.get("note", "")
        phu_cap, pc_count = allow.get(wid, (0.0, 0))   # tổng + số khoản phụ cấp
        weekly = bool(a.get("weekly"))   # nhận lương tuần THEO THÁNG (riêng bảng lương)
        ung_manual, adv_count = adv.get(wid, (0.0, 0))
        # NHẬN LƯƠNG TUẦN → ứng tự động = đúng lương sản phẩm (đã trả theo tuần trong tháng)
        ung_weekly = luong if weekly else 0.0
        ung = ung_manual + ung_weekly
        thuc_lanh = luong + phu_cap + thuong - ung
        out.append({
            "worker_id": wid, "name": w["name"], "wage_type": wt, "weekly": weekly,
            "luong": round(luong), "phu_cap": round(phu_cap), "pc_count": pc_count, "thuong": round(thuong),
            "ung": round(ung), "ung_manual": round(ung_manual), "ung_weekly": round(ung_weekly),
            "adv_count": adv_count, "note": note, "thuc_lanh": round(thuc_lanh),
        })
        tot["luong"] += luong
        tot["phu_cap"] += phu_cap
        tot["thuong"] += thuong
        tot["ung"] += ung
        tot["thuc_lanh"] += thuc_lanh
    return {"ym": ym, "workers": out, "totals": {k: round(v) for k, v in tot.items()}}
