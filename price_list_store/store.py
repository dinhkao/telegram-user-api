"""Bảng giá chung (kv_store['bang_gia_moi']) — đọc/sửa từ webapp. SQLite-only
(không còn Firebase). Shape: {"<id>": {"name": str, "price_list": {SP: int}}}.

Lưu giá = read-modify-write cả blob trong 1 transaction + ghi price_history cho
mỗi SP đổi giá (thêm/sửa/xoá). Khách gắn bảng giá qua customer.price_list == id.
Nối: utils.db, price_list_store.history, order_store (khách)."""
from __future__ import annotations

import json

from utils.db import get_connection, transaction

from .history import create_price_history_table, record_change

_KV_PATH = "bang_gia_moi"


def _load_blob(conn) -> dict:
    row = conn.execute("SELECT value FROM kv_store WHERE path = ?", (_KV_PATH,)).fetchone()
    if not row or not row[0]:
        return {}
    try:
        return json.loads(row[0])
    except Exception:
        return {}


def _save_blob(conn, blob: dict) -> None:
    import time
    conn.execute(
        "INSERT INTO kv_store(path, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(path) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (_KV_PATH, json.dumps(blob, ensure_ascii=False), int(time.time() * 1000)),
    )


def list_all() -> list[dict]:
    """Tất cả bảng giá chung: [{id, name, product_count}] — cho trang danh sách."""
    conn = get_connection()
    try:
        blob = _load_blob(conn)
        out = [
            {"id": lid, "name": (v or {}).get("name") or f"Bảng giá {lid}",
             "product_count": len((v or {}).get("price_list") or {})}
            for lid, v in blob.items()
        ]
        out.sort(key=lambda x: x["name"].lower())
        return out
    finally:
        conn.close()


def get_one(list_id: str) -> dict | None:
    """1 bảng giá: {id, name, items:[{sp,price}]} — items sort theo mã SP."""
    conn = get_connection()
    try:
        blob = _load_blob(conn)
        v = blob.get(str(list_id))
        if v is None:
            return None
        pl = v.get("price_list") or {}
        items = [{"sp": sp, "price": int(pl[sp] or 0)} for sp in sorted(pl.keys())]
        return {"id": str(list_id), "name": v.get("name") or f"Bảng giá {list_id}", "items": items}
    finally:
        conn.close()


def save_prices(list_id: str, items: list[dict], actor: str, *, name: str | None = None) -> dict | None:
    """Ghi lại toàn bộ giá của 1 bảng: diff với bản cũ → price_history mỗi SP đổi.
    items = [{sp, price}]. Trả bảng đã cập nhật (như get_one) hoặc None nếu không có."""
    conn = get_connection()
    try:
        create_price_history_table(conn)
        with transaction(conn):
            blob = _load_blob(conn)
            v = blob.get(str(list_id))
            if v is None:
                return None
            old = {k: int(val or 0) for k, val in (v.get("price_list") or {}).items()}
            new: dict[str, int] = {}
            for it in items:
                sp = str(it.get("sp") or "").strip()
                try:
                    p = int(it.get("price"))
                except (TypeError, ValueError):
                    continue
                if sp and p > 0:
                    new[sp] = p
            # diff → history
            for sp in set(old) | set(new):
                o, n = old.get(sp), new.get(sp)
                if o != n:
                    record_change(conn, list_id, sp, o, n, actor)
            v["price_list"] = new
            if name is not None and name.strip():
                v["name"] = name.strip()
            blob[str(list_id)] = v
            _save_blob(conn, blob)
        return get_one(list_id)
    finally:
        conn.close()


def set_price(list_id: str, sp: str, price, actor: str) -> dict | None:
    """Đổi giá 1 SP → ghi 1 dòng price_history (nếu đổi). Trả bảng đã cập nhật
    (get_one), None nếu không có bảng, {"error":..} nếu SP/giá không hợp lệ."""
    sp = str(sp or "").strip()
    try:
        p = int(price)
    except (TypeError, ValueError):
        return {"error": "giá không hợp lệ"}
    if not sp or p <= 0:
        return {"error": "mã SP / giá không hợp lệ"}
    conn = get_connection()
    try:
        create_price_history_table(conn)
        with transaction(conn):
            blob = _load_blob(conn)
            v = blob.get(str(list_id))
            if v is None:
                return None
            pl = v.get("price_list") or {}
            old = int(pl[sp]) if sp in pl and pl[sp] is not None else None
            if old != p:
                record_change(conn, list_id, sp, old, p, actor)
                pl[sp] = p
                v["price_list"] = pl
                blob[str(list_id)] = v
                _save_blob(conn, blob)
        return get_one(list_id)
    finally:
        conn.close()


def customers_using(list_id: str) -> list[dict]:
    """Khách đang gắn bảng giá này (customer.price_list == id): [{key, name}]."""
    conn = get_connection()
    try:
        # price_list trong JSON có thể là int HOẶC chuỗi → CAST TEXT để khớp cả hai
        rows = conn.execute(
            "SELECT firebase_key, json FROM customers WHERE deleted_at IS NULL "
            "AND CAST(json_extract(json, '$.price_list') AS TEXT) = ?",
            (str(list_id),),
        ).fetchall()
        out = []
        for fk, jtext in rows:
            try:
                d = json.loads(jtext)
            except Exception:
                d = {}
            out.append({"key": fk, "name": d.get("name") or d.get("ten") or fk})
        out.sort(key=lambda x: x["name"].lower())
        return out
    finally:
        conn.close()
