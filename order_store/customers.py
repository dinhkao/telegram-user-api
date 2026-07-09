from __future__ import annotations
import json
import logging
from datetime import UTC, datetime

from vn import vn_normalize
from .search import _invalidate_customer_patterns_cache

log = logging.getLogger("order_store.customers")


def _recent_key(v) -> float:
    """Khoá sắp xếp 'recent' đồng nhất kiểu số — `last_order_at` có thể là epoch
    (int/float), chuỗi ISO, hoặc thiếu. Trộn int↔str khi sort sẽ TypeError."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and v.strip():
        try:
            return datetime.fromisoformat(v.strip().replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def _debt_num(data: dict) -> float:
    try:
        return float(data.get("debt") or 0)
    except (TypeError, ValueError):
        return 0.0


def search_customers(conn, name: str, limit: int = 20, *, sort: str = "name",
                     offset: int = 0, owing: bool = False) -> tuple[list[dict], int]:
    """Return (customers, total_count), phân trang offset.

    Tìm KHÔNG DẤU (vn_normalize) như ô tìm dashboard: gõ 'loan phu' khớp 'Loàn
    Phú'. Khớp trên tên/ten/firebase_key/mẫu nhận diện. 343 khách → quét toàn bộ
    trong bộ nhớ rất nhanh. owing=True → chỉ khách ĐANG NỢ (debt > 0);
    sort='debt' → nợ nhiều nhất trước."""
    q = vn_normalize(name.strip()) if name and name.strip() else ""
    matched: list[dict] = []
    for firebase_key, json_text in conn.execute(
        "SELECT firebase_key, json FROM customers WHERE deleted_at IS NULL"
    ):
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError:
            continue
        if owing and _debt_num(data) <= 0:
            continue
        if q:
            pats = data.get("detectPatterns") or data.get("patterns") or []
            hay = vn_normalize(" ".join([
                str(data.get("name") or ""), str(data.get("ten") or ""),
                str(firebase_key), " ".join(str(p) for p in pats),
            ]))
            if q not in hay:
                continue
        data["_firebase_key"] = firebase_key
        matched.append(data)
    if sort == "recent":
        matched.sort(key=lambda d: _recent_key(d.get("last_order_at")), reverse=True)
    elif sort == "debt":
        matched.sort(key=_debt_num, reverse=True)
    else:
        matched.sort(key=lambda d: vn_normalize(str(d.get("name") or d.get("ten") or d.get("_firebase_key") or "")))
    total = len(matched)
    return matched[offset:offset + limit], total


def customer_stats(conn) -> dict:
    """Tổng quan khách cho KPI dashboard khách: tổng số, số đang nợ, tổng nợ."""
    total = owing = 0
    debt_sum = 0.0
    for (json_text,) in conn.execute("SELECT json FROM customers WHERE deleted_at IS NULL"):
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError:
            continue
        total += 1
        d = _debt_num(data)
        if d > 0:
            owing += 1
            debt_sum += d
    return {"total": total, "owing": owing, "debt_sum": debt_sum}


def add_customer(conn, customer_data: dict) -> tuple[bool, str]:
    """Thêm khách MỚI. Key = danh tính BẤT BIẾN, KHÔNG suy từ tên (lỗi cũ: key =
    slug tên + ON CONFLICT DO UPDATE → 2 khách trùng tên ĐÈ NHAU im lặng, mất data).
    - data có sẵn `firebase_key` → upsert theo key đó (ý định sửa rõ ràng).
    - không có → sinh key epoch-ms duy nhất; trùng tên với khách sẵn có vẫn tạo
      KHÁCH MỚI riêng, chỉ cảnh báo trong message."""
    name = customer_data.get("name") or customer_data.get("ten") or "unknown"
    now = int(datetime.now(UTC).timestamp() * 1000)  # cột updated_at = epoch ms (bigint)
    explicit_key = str(customer_data.get("firebase_key") or "").strip()
    try:
        if explicit_key:
            conn.execute(
                """INSERT INTO customers (firebase_key, json, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(firebase_key) DO UPDATE SET json=excluded.json, updated_at=excluded.updated_at""",
                (explicit_key, json.dumps(customer_data, ensure_ascii=False), now),
            )
            conn.commit()
            _invalidate_customer_patterns_cache()
            return True, f"✅ Đã thêm/sửa khách hàng: {name} (key {explicit_key})"
        key_ms = now
        key = str(key_ms)
        while conn.execute("SELECT 1 FROM customers WHERE firebase_key = ?", (key,)).fetchone():
            key_ms += 1
            key = str(key_ms)
        dup = conn.execute(
            "SELECT firebase_key FROM customers WHERE deleted_at IS NULL "
            "AND LOWER(COALESCE(json_extract(json, '$.name'), json_extract(json, '$.ten'), '')) = LOWER(?)",
            (str(name),),
        ).fetchone()
        conn.execute(
            "INSERT INTO customers (firebase_key, json, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(customer_data, ensure_ascii=False), now),
        )
        conn.commit()
        _invalidate_customer_patterns_cache()
        msg = f"✅ Đã thêm khách hàng: {name} (key {key})"
        if dup:
            msg += f"\n⚠️ Trùng tên với khách sẵn có (key {dup[0]}) — đây là KHÁCH MỚI riêng, không đè."
        return True, msg
    except Exception as e:
        return False, f"❌ Lỗi thêm khách hàng: {e}"


def update_customer(conn, firebase_key: str, customer_data: dict) -> tuple[bool, str]:
    now = int(datetime.now(UTC).timestamp() * 1000)  # cột updated_at = epoch ms (bigint)
    cur = conn.execute("UPDATE customers SET json = ?, updated_at = ? WHERE firebase_key = ? AND deleted_at IS NULL", (json.dumps(customer_data, ensure_ascii=False), now, firebase_key))
    conn.commit(); _invalidate_customer_patterns_cache()
    return (False, f"❌ Không tìm thấy khách hàng: {firebase_key}") if cur.rowcount == 0 else (True, f"✅ Đã cập nhật: {firebase_key}")


def get_customer_kv_id(conn, firebase_key: str) -> int | None:
    try:
        row = conn.execute("SELECT json FROM customers WHERE firebase_key = ? AND deleted_at IS NULL", (firebase_key,)).fetchone()
        return None if not row else json.loads(row["json"]).get("kh_id")
    except Exception:
        return None


def touch_customer_last_order(conn, firebase_key: str) -> None:
    """Cập nhật last_order_at cho khách hàng khi có đơn mới hoặc gán khách."""
    if not firebase_key:
        return
    try:
        row = conn.execute(
            "SELECT json FROM customers WHERE firebase_key = ? AND deleted_at IS NULL",
            (firebase_key,),
        ).fetchone()
        if not row:
            return
        data = json.loads(row["json"])
        data["last_order_at"] = datetime.now(UTC).isoformat()
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        conn.execute(
            "UPDATE customers SET json = ?, updated_at = ? WHERE firebase_key = ?",
            (json.dumps(data, ensure_ascii=False), now_ms, firebase_key),
        )
        conn.commit()
    except Exception as e:
        log.warning("touch_customer_last_order failed key=%s: %s", firebase_key, e)


def update_customer_debt(conn, firebase_key: str, debt: float | int) -> None:
    """Cập nhật debt + debt_updated_at trong customer JSON khi có giá trị mới từ KiotViet."""
    if not firebase_key or debt is None:
        return
    try:
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        conn.execute(
            "UPDATE customers SET json = json_set(json_set(json, '$.debt', ?), '$.debt_updated_at', ?), updated_at = ? WHERE firebase_key = ? AND deleted_at IS NULL",
            (debt, now_ms, now_ms, firebase_key),
        )
        conn.commit()
    except Exception as e:
        log.warning("update_customer_debt failed key=%s: %s", firebase_key, e)


def get_customer_by_key(conn, firebase_key: str) -> dict | None:
    try:
        row = conn.execute("SELECT json FROM customers WHERE firebase_key = ? AND deleted_at IS NULL", (firebase_key,)).fetchone()
        return None if not row else json.loads(row["json"])
    except Exception:
        return None
