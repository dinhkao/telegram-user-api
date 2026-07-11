"""Bảng LƯƠNG theo sản phẩm (đơn giá / 1 cây SP) — bảng production_wages (app.db).

NHẠY CẢM: chỉ đọc/ghi qua endpoint đã chặn role văn phòng (server_app/wage_routes,
production_wages). Tiền công = số cây × luong[mã]. Sửa từ webapp `#/luong-sp`;
seed 1 lần từ bảng cứng cũ (_SEED, INSERT OR IGNORE — idempotent). Khớp theo MÃ
HIỆN HÀNH (IN HOA); SP không có trong bảng → lương 0 (liệt kê ở `missing_wage`).
Đọc nóng qua cache module (invalidate khi ghi — 1 process nên đủ). Nối: utils.db.
"""
from __future__ import annotations

from utils.db import transaction

# Bảng cứng cũ — CHỈ để seed lần đầu; nguồn sự thật giờ là bảng production_wages.
_SEED: dict[str, dict] = {
    "K10LT":    {"mam": 3.0, "chao": 18.0, "luong": 1200},
    "K10LV85":  {"mam": 3.0, "chao": 25.0, "luong": 1000},
    "K10LV87":  {"mam": 3.0, "chao": 19.0, "luong": 1100},
    "K10NV60":  {"mam": 5.0, "chao": None, "luong": 500},
    "K10TV80":  {"mam": 4.0, "chao": 26.0, "luong": 800},
    "K2L":      {"mam": 3.5, "chao": 31.0, "luong": 720},
    "K2NT":     {"mam": 6.0, "chao": 38.0, "luong": 420},
    "K2NT128":  {"mam": 6.0, "chao": None, "luong": 420},
    "K2NV120":  {"mam": 6.0, "chao": 54.0, "luong": 380},
    "K2NV128":  {"mam": 6.0, "chao": 47.0, "luong": 380},
    "KDDT":     {"mam": 5.0, "chao": None, "luong": 800},
    "KE":       {"mam": 6.0, "chao": None, "luong": 500},
    "KHT":      {"mam": 8.0, "chao": None, "luong": 400},
    "K13NV-58": {"mam": 4.0, "chao": None, "luong": 750},
    "KD2M":     {"mam": 6.0, "chao": 41.0, "luong": 900},
    "KDBN2M":   {"mam": 4.5, "chao": 30.0, "luong": 1000},
    "KDBN1L":   {"mam": 4.0, "chao": 28.0, "luong": 1000},
    "K1L":      {"mam": 4.0, "chao": 25.0, "luong": 720},
    "K2LBN":    {"mam": 3.5, "chao": 31.0, "luong": 720},
}

# code (IN HOA) → {"luong": đ/cây, "mam": ..., "chao": ...} — nạp lười từ DB.
_cache: dict[str, dict] | None = None


def ensure_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS production_wages (
            code       TEXT PRIMARY KEY,
            luong      REAL NOT NULL DEFAULT 0,
            mam        REAL,
            chao       REAL,
            updated_at TEXT DEFAULT (datetime('now', '+7 hours')),
            updated_by TEXT DEFAULT ''
        )
        """
    )
    conn.executemany(
        "INSERT OR IGNORE INTO production_wages (code, luong, mam, chao) VALUES (?, ?, ?, ?)",
        [(c, v["luong"], v.get("mam"), v.get("chao")) for c, v in _SEED.items()],
    )
    conn.commit()


def invalidate_cache() -> None:
    global _cache
    _cache = None


def _load() -> dict[str, dict]:
    global _cache
    if _cache is None:
        from utils.db import get_connection
        conn = get_connection()
        try:
            ensure_table(conn)
            rows = conn.execute("SELECT code, luong, mam, chao FROM production_wages").fetchall()
            _cache = {
                r["code"]: {"luong": float(r["luong"] or 0), "mam": r["mam"], "chao": r["chao"]}
                for r in rows
            }
        finally:
            conn.close()
    return _cache


def wage_per_cay(code: str | None) -> float:
    """Đơn giá lương / 1 cây của SP (0 nếu chưa có trong bảng)."""
    return float(_load().get(str(code or "").strip().upper(), {}).get("luong") or 0)


def has_wage(code: str | None) -> bool:
    return wage_per_cay(code) > 0


def wage_for_code(conn, code: str | None) -> float:
    """Đơn giá bảng lương hiện tại của 1 mã, đọc qua `conn` truyền vào (không qua
    cache module) — dùng để CHỐT snapshot vào phiếu SX (queries.set_sp)."""
    ensure_table(conn)
    c = str(code or "").strip().upper()
    r = conn.execute("SELECT luong FROM production_wages WHERE code = ?", (c,)).fetchone()
    return float(r["luong"] or 0) if r else 0.0


def list_wages(conn) -> list[dict]:
    """Mọi entry lương (kèm tên SP hiện hành nếu khớp mã) — cho trang sửa lương."""
    ensure_table(conn)
    rows = conn.execute(
        "SELECT w.code, w.luong, w.mam, w.chao, w.updated_at, w.updated_by, p.name AS product_name "
        "FROM production_wages w "
        "LEFT JOIN products p ON UPPER(p.code) = w.code "
        "ORDER BY w.code"
    ).fetchall()
    return [
        {"code": r["code"], "luong": float(r["luong"] or 0), "mam": r["mam"], "chao": r["chao"],
         "updated_at": r["updated_at"] or "", "updated_by": r["updated_by"] or "",
         "product_name": r["product_name"] or ""}
        for r in rows
    ]


def set_wage(conn, code: str, luong: float, by: str = "") -> None:
    """Đặt đơn giá lương 1 mã (IN HOA). luong <= 0 → xoá entry (về missing_wage)."""
    ensure_table(conn)
    c = str(code or "").strip().upper()
    if not c:
        raise ValueError("Thiếu mã SP")
    with transaction(conn):
        if luong and luong > 0:
            conn.execute(
                "INSERT INTO production_wages (code, luong, updated_at, updated_by) "
                "VALUES (?, ?, datetime('now', '+7 hours'), ?) "
                "ON CONFLICT(code) DO UPDATE SET luong = excluded.luong, "
                "updated_at = excluded.updated_at, updated_by = excluded.updated_by",
                (c, float(luong), by or ""),
            )
        else:
            conn.execute("DELETE FROM production_wages WHERE code = ?", (c,))
    invalidate_cache()
