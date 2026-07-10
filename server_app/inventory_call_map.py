"""Bản đồ SỐ GỌI thùng — GET /api/inventory/call-numbers.

Tình trạng cả 999 số gọi (001..999): số nào ĐANG CHIẾM (thùng còn hàng hoặc vô
hiệu — nhãn còn dán trên thùng thật) vs CÒN TRỐNG (cấp phát được). Cùng luật với
inventory_store.add_boxes (số chiếm = disabled=1 OR quantity > Σ đã xuất). Kèm
điểm xoay `last` (số thùng tạo gần nhất) + `next` (số sẽ cấp kế tiếp).
Đọc: inventory_boxes, box_allocations, products, inventory_places. Không ghi.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from order_db import _get_connection
from inventory_store.domain import call_code, code_call_number, next_call_numbers


# 1 số gọi được xem là "còn hàng" (in_stock) ưu tiên hơn "vô hiệu" khi trùng số.
def _better(a: dict, b: dict) -> dict:
    """Chọn thùng đại diện khi 2 thùng cùng số gọi (hiếm): còn hàng > vô hiệu,
    rồi remaining lớn hơn, rồi id lớn hơn (mới hơn)."""
    ka = (0 if a["disabled"] else 1, a["remaining"], a["box_id"])
    kb = (0 if b["disabled"] else 1, b["remaining"], b["box_id"])
    return a if ka >= kb else b


def compute_call_map() -> dict:
    conn = _get_connection()
    try:
        return _compute(conn)
    finally:
        conn.close()


def _compute(conn) -> dict:
    rows = conn.execute(
        "SELECT b.id, b.box_code, b.disabled, b.mfg_date, b.note, "
        "  b.quantity - COALESCE((SELECT SUM(a.quantity) FROM box_allocations a WHERE a.box_id=b.id),0) AS remaining, "
        "  COALESCE(p.code, b.product_code) AS product_code, COALESCE(p.name,'') AS product_name, "
        "  pl.name AS place_name "
        "FROM inventory_boxes b "
        "LEFT JOIN products p ON p.id = b.product_id "
        "LEFT JOIN inventory_places pl ON pl.id = b.place_id "
        "WHERE b.disabled = 1 "
        "   OR b.quantity > COALESCE((SELECT SUM(a.quantity) FROM box_allocations a WHERE a.box_id=b.id),0)"
    ).fetchall()

    occupied: dict = {}
    collisions = 0
    for r in rows:
        n = code_call_number(r["box_code"])
        if not (1 <= n <= 999):
            continue                       # mã không nhận ra / ngoài dải → bỏ (không chiếm số)
        disabled = bool(r["disabled"])
        entry = {
            "n": n, "code": call_code(n), "box_id": r["id"], "box_code": r["box_code"],
            "remaining": round(float(r["remaining"] or 0), 3),
            "disabled": disabled,
            "product_code": r["product_code"] or "", "product_name": r["product_name"] or "",
            "place_name": r["place_name"] or "", "mfg_date": r["mfg_date"] or "",
        }
        if n in occupied:
            collisions += 1
            occupied[n] = _better(occupied[n], entry)
        else:
            occupied[n] = entry

    last_row = conn.execute("SELECT box_code FROM inventory_boxes ORDER BY id DESC LIMIT 1").fetchone()
    last = code_call_number(last_row["box_code"]) if last_row else 0
    taken = set(occupied.keys())
    try:
        nxt = next_call_numbers(last, taken, 1)[0]
    except ValueError:
        nxt = None                          # đã dùng hết 999 số

    n_disabled = sum(1 for e in occupied.values() if e["disabled"])
    n_instock = len(occupied) - n_disabled
    return {
        "ok": True,
        "total": 999,
        "occupied": [occupied[k] for k in sorted(occupied)],
        "last": last,
        "next": nxt,
        "counts": {
            "occupied": len(occupied),
            "free": 999 - len(occupied),
            "in_stock": n_instock,
            "disabled": n_disabled,
            "collisions": collisions,
        },
    }


async def call_map_handler(request: web.Request):
    data = await asyncio.to_thread(compute_call_map)
    return web.json_response(data)
