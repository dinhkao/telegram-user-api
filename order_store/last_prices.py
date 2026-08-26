"""Giá BÁN GẦN NHẤT của từng SP theo KHÁCH — lấy từ hoá đơn các đơn cũ.

Dùng khi parse hoá đơn lúc tạo/sửa đơn (`order_store.free_text`,
`order_store.comma_parser`): giá mặc định của 1 item ưu tiên GIÁ KHÁCH ĐÓ ĐÃ MUA
LẦN GẦN NHẤT, không có mới rơi về bảng giá (`order_store.search.get_customer_price_list`).
Giá gõ tay trong text vẫn luôn thắng cả hai.

Khớp SP theo DANH TÍNH: `sp_id` (đơn mới) hoặc mã `sp` + alias mã cũ
(`product_store.code_alias_map`) → key trả về là MÃ HIỆN HÀNH.
Cache RAM theo khách, TTL ngắn (parse chạy mỗi lần gõ ở trang tạo đơn).
"""
from __future__ import annotations

import json
import time

_ORDERS_SCANNED = 30      # số đơn gần nhất của khách đem ra dò giá
_TTL = 60                 # giây
_cache: dict[str, tuple[float, dict[str, int]]] = {}


def invalidate_last_price_cache(kh_id=None) -> None:
    """Xoá cache (1 khách hoặc toàn bộ) — gọi khi biết hoá đơn vừa đổi."""
    if kh_id is None:
        _cache.clear()
    else:
        _cache.pop(str(kh_id).strip(), None)


_SELECT = """
    SELECT coalesce(json_extract(json, '$.invoice'),
                    json_extract(json, '$.invoice_items')) AS inv
    FROM orders
    WHERE deleted_at IS NULL AND %s = ?
    ORDER BY order_created DESC, thread_id DESC
    LIMIT ?
"""
_SQL_BY_COL = _SELECT % "cust_key"
_SQL_BY_EXPR = _SELECT % (
    "coalesce(json_extract(json, '$.khach_hang_id'), json_extract(json, '$.khID'))"
)


def _code_maps(conn) -> tuple[dict, dict]:
    """(id → mã hiện hành, mã cũ → mã hiện hành)."""
    from product_store.queries import get_all_products
    by_id = {p["id"]: str(p["code"]).upper() for p in (get_all_products(conn) or []) if p.get("id") is not None}
    alias: dict[str, str] = {}
    try:
        from product_store import code_alias_map
        alias = {str(old).upper(): by_id[pid] for old, pid in code_alias_map(conn).items() if pid in by_id}
    except Exception:  # noqa: BLE001 — DB test cũ thiếu bảng history
        pass
    return by_id, alias


def _price(raw) -> int:
    try:
        v = int(float(raw))
    except (TypeError, ValueError):
        return 0
    return v if v > 0 else 0


_HIST_SELECT = """
    SELECT thread_id, order_created,
           coalesce(json_extract(json, '$.invoice'),
                    json_extract(json, '$.invoice_items')) AS inv
    FROM orders
    WHERE deleted_at IS NULL AND %s = ?
    ORDER BY order_created DESC, thread_id DESC
    LIMIT ?
"""
_HSQL_BY_COL = _HIST_SELECT % "cust_key"
_HSQL_BY_EXPR = _HIST_SELECT % (
    "coalesce(json_extract(json, '$.khach_hang_id'), json_extract(json, '$.khID'))"
)


def price_history(conn, kh_id: str | int | None, per_code: int = 5,
                  limit: int = _ORDERS_SCANNED) -> dict[str, list[dict]]:
    """{MÃ HIỆN HÀNH: [{price, sl, thread_id, date 'dd/mm'}]} — đơn giá của khách
    trong tối đa `per_code` ĐƠN GẦN NHẤT có mã đó (đơn mới trước, mỗi đơn 1 dòng).
    Cho trang sửa hoá đơn hiện lịch sử giá từng món. Không cache — gọi 1 lần/lần
    mở trang (POST /api/customer/price-history)."""
    key = str(kh_id or "").strip()
    if not key or conn is None:
        return {}
    n = max(1, int(limit))
    try:
        rows = conn.execute(_HSQL_BY_COL, (key, n)).fetchall()
    except Exception:  # noqa: BLE001 — chưa có cột cust_key (DB cũ/test)
        try:
            rows = conn.execute(_HSQL_BY_EXPR, (key, n)).fetchall()
        except Exception:  # noqa: BLE001
            return {}
    by_id, alias = _code_maps(conn) if rows else ({}, {})
    out: dict[str, list[dict]] = {}
    for row in rows:                                  # đơn mới → cũ
        try:
            items = json.loads(row["inv"]) if row["inv"] else []
        except (TypeError, ValueError):
            continue
        if not isinstance(items, list):
            continue
        created = str(row["order_created"] or "")
        date = f"{created[8:10]}/{created[5:7]}" if len(created) >= 10 else ""
        seen = set()                                  # 1 đơn chỉ tính 1 dòng/mã
        for it in items:
            if not isinstance(it, dict):
                continue
            code = by_id.get(it.get("sp_id")) if it.get("sp_id") is not None else None
            if not code:
                raw = str(it.get("sp") or "").upper().strip()
                code = alias.get(raw, raw)
            if not code or code in seen:
                continue
            price = _price(it.get("price"))
            if not price:
                continue
            lst = out.setdefault(code, [])
            if len(lst) >= per_code:
                continue
            try:
                sl = float(it.get("sl") or 0)
            except (TypeError, ValueError):
                sl = 0.0
            lst.append({"price": price, "sl": sl,
                        "thread_id": row["thread_id"], "date": date})
            seen.add(code)
    return out


def last_order_prices(conn, kh_id: str | int | None, limit: int = _ORDERS_SCANNED) -> dict[str, int]:
    """{MÃ HIỆN HÀNH: giá bán lần gần nhất} của khách. Rỗng nếu chưa mua bao giờ."""
    key = str(kh_id or "").strip()
    if not key or conn is None:
        return {}
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    n = max(1, int(limit))
    # Lọc qua cột generated `cust_key` (+ idx_orders_cust_created, xem
    # server_app.orders_db.ensure_orders_stats_columns): viết thẳng biểu thức
    # json_extract thì SQLite QUÉT TRỌN 18k đơn — khách chưa mua bao giờ tốn ~70ms
    # chặn event loop. DB cũ/test chưa có cột → rơi về biểu thức gốc (cùng kết quả).
    try:
        rows = conn.execute(_SQL_BY_COL, (key, n)).fetchall()
    except Exception:  # noqa: BLE001 — chưa có cột cust_key
        try:
            rows = conn.execute(_SQL_BY_EXPR, (key, n)).fetchall()
        except Exception:  # noqa: BLE001 — thiếu cột/bảng (test) → coi như chưa có lịch sử
            return {}
    by_id, alias = _code_maps(conn) if rows else ({}, {})
    out: dict[str, int] = {}
    for row in rows:                                  # đơn mới → cũ
        try:
            items = json.loads(row[0]) if row[0] else []
        except (TypeError, ValueError):
            continue
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            code = by_id.get(it.get("sp_id")) if it.get("sp_id") is not None else None
            if not code:
                raw = str(it.get("sp") or "").upper().strip()
                code = alias.get(raw, raw)
            if not code or code in out:               # đơn mới nhất thắng
                continue
            price = _price(it.get("price"))
            if price:
                out[code] = price
    _cache[key] = (now, out)
    return out
