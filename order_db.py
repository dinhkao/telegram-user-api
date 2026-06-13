"""order_db.py — Read/write order task_status in shared SQLite.

Shares the same database as final_telegram (app.db).
WAL mode write connection — concurrent reads with one writer.
"""
from __future__ import annotations
import json
import logging
import re
import os
import sqlite3
import time

log = logging.getLogger("order_db")

SHARED_DB_PATH = os.path.expanduser(
    os.getenv("SHARED_DB_PATH", "~/Documents/final_telegram/data/app.db")
)

# Mirror fields map: task_type -> order root boolean field
MIRROR_FIELDS = {
    "soan_hang": "soan",
    "giao_hang": "giao",
    "nop_tien": "nop",
    "nhan_tien": "nhan",
}


def _get_connection():
    """Open a WAL write connection."""
    conn = sqlite3.connect(
        SHARED_DB_PATH,
        check_same_thread=False,
        isolation_level=None,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def get_order_by_thread_id(conn, thread_id: int, *, include_deleted: bool = True) -> dict | None:
    """Read full order JSON by thread_id. Returns None if not found.
    Always includes deleted orders (del=true). Use include_deleted=False for list views."""
    where = "WHERE thread_id = ?" if include_deleted else "WHERE thread_id = ? AND deleted_at IS NULL"
    row = conn.execute(f"SELECT json FROM orders {where}", (thread_id,)).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None


def _get_order_firebase_key(conn, thread_id: int) -> str | None:
    """Get the firebase_key for an order by thread_id."""
    row = conn.execute(
        "SELECT firebase_key FROM orders WHERE thread_id = ? AND deleted_at IS NULL",
        (thread_id,),
    ).fetchone()
    return row["firebase_key"] if row else None


def _save_order(conn, thread_id: int, data: dict) -> bool:
    """Save order JSON back to SQLite. Returns True on success."""
    try:
        conn.execute(
            "UPDATE orders SET json = ?, updated_at = ? WHERE thread_id = ? AND deleted_at IS NULL",
            (json.dumps(data, ensure_ascii=False), int(time.time() * 1000), thread_id),
        )
        return True
    except Exception as e:
        log.error("Failed to save order thread=%d: %s", thread_id, e)
        return False


def _all_steps_done(task_status: dict) -> bool:
    """Check if all 5 core steps are done or skipped."""
    required = ["ban_hd", "soan_hang", "giao_hang", "nop_tien", "nhan_tien"]
    return all(
        task_status.get(step, {}).get("done") or task_status.get(step, {}).get("skip", False)
        for step in required
    )


def set_task_status(conn, thread_id: int, task_type: str, user_id: int | None, *, skip: bool = False, done: bool = True, note: str = "") -> bool:
    """Write task_status entry and mirror boolean. Returns True on success."""
    data = get_order_by_thread_id(conn, thread_id)
    if data is None:
        log.warning("set_task_status: order not found thread=%d", thread_id)
        return False

    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    payload = {"done": done, "by": user_id, "at": now_iso, "skip": skip}
    if note:
        payload["note"] = note

    # Update task_status
    task_status = data.get("task_status") or {}
    task_status[task_type] = payload
    data["task_status"] = task_status

    # Update mirror boolean
    mirror_field = MIRROR_FIELDS.get(task_type)
    if mirror_field:
        data[mirror_field] = bool(done or skip)

    # Set done_after_20250124 when all 5 steps complete
    if _all_steps_done(task_status):
        data["done_after_20250124"] = True

    # Set flow_version
    if "flow_version" not in data:
        data["flow_version"] = 2

    return _save_order(conn, thread_id, data)


def clear_task_status(conn, thread_id: int, task_type: str, user_id: int | None) -> bool:
    """Remove a task_status entry (undo). Returns True on success."""
    data = get_order_by_thread_id(conn, thread_id)
    if data is None:
        log.warning("clear_task_status: order not found thread=%d", thread_id)
        return False

    task_status = data.get("task_status") or {}
    if task_type in task_status:
        del task_status[task_type]

    if task_status:
        data["task_status"] = task_status
    elif "task_status" in data:
        del data["task_status"]

    # Reset mirror boolean
    mirror_field = MIRROR_FIELDS.get(task_type)
    if mirror_field:
        data[mirror_field] = False

    return _save_order(conn, thread_id, data)
# ── Phase A: Extended functions for full command migration ────────────

from datetime import datetime, timezone, UTC
import http.client


def delete_order(conn, thread_id: int, force: bool = False) -> tuple[bool, str]:
    """Soft-delete an order. Returns (ok, message)."""
    cur = conn.execute(
        "SELECT firebase_key, json FROM orders WHERE thread_id = ? AND deleted_at IS NULL",
        (thread_id,),
    )
    row = cur.fetchone()
    if not row:
        return False, "Không tìm thấy đơn hàng"
    firebase_key, json_text = row["firebase_key"], row["json"]
    order = json.loads(json_text or "{}")
    if not force and order.get("trang_thai") == "Done":
        return False, "Đơn hàng đã hoàn thành, dùng `del hd` để xóa cưỡng chế"
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    order["del"] = True
    order["deleted_at"] = now
    conn.execute(
        "UPDATE orders SET json = ?, deleted_at = ? WHERE thread_id = ?",
        (json.dumps(order, ensure_ascii=False), now, thread_id),
    )
    conn.commit()
    return True, f"🗑️ Đã xóa đơn hàng (key={firebase_key})"


def search_customers(conn, name: str, limit: int = 20) -> list[dict]:
    """Search customers by name (case-insensitive LIKE)."""
    pattern = f"%{name}%"
    cur = conn.execute(
        """SELECT json FROM customers WHERE deleted_at IS NULL
           AND (json LIKE ? OR firebase_key LIKE ?)
           ORDER BY firebase_key LIMIT ?""",
        (pattern, pattern, limit),
    )
    results = []
    for (json_text,) in cur:
        try:
            results.append(json.loads(json_text))
        except json.JSONDecodeError:
            continue
    return results


def add_customer(conn, customer_data: dict) -> tuple[bool, str]:
    """Insert or update a customer. Returns (ok, message)."""
    name = customer_data.get("name") or customer_data.get("ten") or "unknown"
    firebase_key = name.lower().replace(" ", "_")
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    try:
        conn.execute(
            """INSERT INTO customers (firebase_key, json, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(firebase_key) DO UPDATE SET json=excluded.json, updated_at=excluded.updated_at""",
            (firebase_key, json.dumps(customer_data, ensure_ascii=False), now),
        )
        conn.commit()
        return True, f"✅ Đã thêm/sửa khách hàng: {name}"
    except Exception as e:
        return False, f"❌ Lỗi thêm khách hàng: {e}"


def update_customer(conn, firebase_key: str, customer_data: dict) -> tuple[bool, str]:
    """Update an existing customer by key. Returns (ok, message)."""
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    cur = conn.execute(
        "UPDATE customers SET json = ?, updated_at = ? WHERE firebase_key = ? AND deleted_at IS NULL",
        (json.dumps(customer_data, ensure_ascii=False), now, firebase_key),
    )
    conn.commit()
    if cur.rowcount == 0:
        return False, f"❌ Không tìm thấy khách hàng: {firebase_key}"
    return True, f"✅ Đã cập nhật: {firebase_key}"


def get_customer_kv_id(conn, firebase_key: str) -> int | None:
    """Return the KiotViet customer ID (kh_id) for a given Firebase customer key."""
    try:
        cur = conn.execute("SELECT json FROM customers WHERE firebase_key = ? AND deleted_at IS NULL", (firebase_key,))
        row = cur.fetchone()
        if not row:
            return None
        data = json.loads(row["json"])
        return data.get("kh_id")
    except Exception:
        return None


def get_customer_by_key(conn, firebase_key: str) -> dict | None:
    """Return full customer JSON for a given Firebase customer key."""
    try:
        cur = conn.execute("SELECT json FROM customers WHERE firebase_key = ? AND deleted_at IS NULL", (firebase_key,))
        row = cur.fetchone()
        if not row:
            return None
        return json.loads(row["json"])
    except Exception:
        return None
def search_products(conn, code_or_name: str, limit: int = 15) -> list[dict]:
    """Search products — tries kv_store, falls back to KiotViet API."""
    pattern = f"%{code_or_name}%"
    # Try kv_store (mirrored Firebase KV data)
    try:
        cur = conn.execute(
            "SELECT value FROM kv_store WHERE path LIKE ? ORDER BY path LIMIT ?",
            (f"%product%{pattern}%", limit),
        )
        results = []
        for (json_text,) in cur:
            try:
                d = json.loads(json_text)
                if isinstance(d, dict):
                    results.append(d)
            except json.JSONDecodeError:
                continue
        if results:
            return results
    except Exception:
        pass
    # Fallback: KiotViet API
    try:
        from kiotviet import search_products_kv
        results = search_products_kv(code_or_name, limit)
        if results:
            return results
    except Exception:
        pass
    return []


def get_all_tasks(conn) -> list[dict]:
    """Get all active tasks across all orders."""
    cur = conn.execute(
        """SELECT thread_id, firebase_key, json FROM orders
           WHERE deleted_at IS NULL AND json IS NOT NULL"""
    )
    tasks = []
    for row in cur:
        try:
            order = json.loads(row["json"])
            ts = order.get("task_status", {})
            if ts:
                tasks.append({
                    "thread_id": row["thread_id"],
                    "firebase_key": row["firebase_key"],
                    "task_status": ts,
                    "name": order.get("khach_hang", order.get("name", "")),
                    "flow_version": order.get("flow_version"),
                })
        except json.JSONDecodeError:
            continue
    return tasks


def delete_all_tasks(conn) -> tuple[int, str]:
    """Delete all task_status from all orders. Returns (count, message)."""
    cur = conn.execute("SELECT thread_id, json FROM orders WHERE deleted_at IS NULL")
    count = 0
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    for row in cur:
        json_text = row["json"]
        if not json_text:
            continue
        order = json.loads(json_text)
        if "task_status" in order:
            del order["task_status"]
            conn.execute(
                "UPDATE orders SET json = ?, updated_at = ? WHERE thread_id = ?",
                (json.dumps(order, ensure_ascii=False), now, row["thread_id"]),
            )
            count += 1
    conn.commit()
    return count, f"✅ Đã xóa task của {count} đơn hàng"


def sort_tasks(conn) -> tuple[int, str]:
    """Return sorted task count (sorting is view-only, just return count)."""
    tasks = get_all_tasks(conn)
    return len(tasks), f"✅ Đã sắp xếp {len(tasks)} task"


def migrate_tasks_to_v2(conn) -> tuple[int, str]:
    """Migrate v1 task format to v2."""
    cur = conn.execute("SELECT thread_id, json FROM orders WHERE deleted_at IS NULL")
    count = 0
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    for row in cur:
        json_text = row["json"]
        if not json_text:
            continue
        order = json.loads(json_text)
        if order.get("flow_version") != 2:
            order["flow_version"] = 2
            order["done_after_20250124"] = True
            conn.execute(
                "UPDATE orders SET json = ?, updated_at = ? WHERE thread_id = ?",
                (json.dumps(order, ensure_ascii=False), now, row["thread_id"]),
            )
            count += 1
    conn.commit()
    return count, f"✅ Đã migrate {count} đơn sang V2"


def get_order_json(conn, thread_id: int) -> dict | None:
    """Get order as parsed JSON dict."""
    cur = conn.execute(
        "SELECT json FROM orders WHERE thread_id = ? AND deleted_at IS NULL",
        (thread_id,),
    )
    row = cur.fetchone()
    if not row or not row["json"]:
        return None
    return json.loads(row["json"])


FINAL_TELEGRAM_URL = os.getenv("FINAL_TELEGRAM_URL", "http://localhost:3000")


def _call_final_telegram(endpoint: str, body: dict, timeout: int = 10) -> dict | None:
    """Helper: POST to final_telegram API. Returns parsed JSON or None."""
    host_port = FINAL_TELEGRAM_URL.replace("http://", "").replace("https://", "")
    host, _, port_str = host_port.partition(":")
    port = int(port_str) if port_str else 80
    try:
        conn_http = http.client.HTTPConnection(host, port, timeout=timeout)
        payload = json.dumps(body, ensure_ascii=False).encode()
        conn_http.request("POST", endpoint, payload, {"Content-Type": "application/json"})
        resp = conn_http.getresponse()
        data = json.loads(resp.read())
        conn_http.close()
        return data
    except Exception as e:
        log.error("_call_final_telegram %s: %s", endpoint, e)
        return None


def get_order_html(conn, thread_id: int) -> str:
    """Generate order HTML view via final_telegram API."""
    result = _call_final_telegram("/api/order/get-html", {"thread_id": thread_id})
    if not result:
        return "❌ Không thể lấy HTML"
    return result.get("html", "") or "Không có HTML"


def set_order_flag(conn, thread_id: int, flag_name: str, value: bool | str) -> tuple[bool, str]:
    """Set a boolean or string flag on an order. Returns (ok, message)."""
    data = get_order_by_thread_id(conn, thread_id)
    if data is None:
        return False, "Không tìm thấy đơn hàng"
    data[flag_name] = value
    data["updated_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    ok = _save_order(conn, thread_id, data)
    if ok:
        return True, f"✅ Đã cập nhật {flag_name}"
    return False, "❌ Lỗi lưu đơn hàng"

# ── Comma text parser ───────────────────────────────────────────────

_RE_NO_QC = re.compile(
    r"^\s*([A-Za-z0-9-]+)\s{2,}(\d+(?:\.\d+)?)(?:\s+(\d+(?:\.\d+)?))?(?:\s+(.+))?\s*$"
)

_RE_QC_T = re.compile(r"^\d+t$")
_RE_QC_B = re.compile(r"^\d+b$")
_RE_QC_TB = re.compile(r"^([\d.]+)t([\d.]+)b$")
_RE_QC_TX_BX = re.compile(r"^(t\d+|b\d+)$")


def _parse_no_qc(line: str) -> dict | None:
    """Parse a no-QC line: 'KDDT  3  130000  note' → {sp, sl1qc, price, note}."""
    m = _RE_NO_QC.match(line)
    if not m:
        return None
    return {
        "sp": m.group(1),
        "sl1qc": m.group(2),
        "price": m.group(3),
        "note": m.group(4),
    }


def _parse_qc(qc: str) -> tuple[str | None, list[int]]:
    """Parse quantity code. Returns (qc_type, so_qc)."""
    if not qc:
        return None, [1]
    if _RE_QC_T.match(qc):
        return "t", [int(qc[:-1])]
    if _RE_QC_B.match(qc):
        return "b", [int(qc[:-1])]
    m = _RE_QC_TB.match(qc)
    if m:
        return "tb", [int(m.group(1)), int(m.group(2))]
    if _RE_QC_TX_BX.match(qc):
        return qc, [1]
    return None, [1]


def get_customer_price_list(conn, kh_id: str | int) -> dict[str, int]:
    """Get product → price map for a customer's assigned price list.

    Mirrors Node.js KhachHang.getPriceList():
    1. Reads bang_gia_moi/{price_list_id}/price_list from kv_store
    2. Merges with personal_price_list (customer-specific overrides take precedence)
    3. Returns combined price map (personal overrides general)
    """
    cur = conn.execute("SELECT json FROM customers WHERE firebase_key = ? AND deleted_at IS NULL", (str(kh_id),))
    row = cur.fetchone()
    if not row:
        return {}
    cust = json.loads(row["json"])

    price_list = {}

    # 1. General price list from bang_gia_moi/{priceListID}/price_list
    price_list_id = cust.get("price_list")
    if price_list_id:
        cur = conn.execute("SELECT value FROM kv_store WHERE path = 'bang_gia_moi'")
        row = cur.fetchone()
        if row and row["value"]:
            all_lists = json.loads(row["value"])
            price_list = all_lists.get(str(price_list_id), {}).get("price_list", {})

    # 2. Merge personal_price_list (takes precedence over general)
    personal = cust.get("personal_price_list")
    if personal and isinstance(personal, dict):
        price_list = {**price_list, **personal}

    return price_list


def parse_comma_text(text: str, conn, kh_id: str | int | None) -> list[dict]:
    """Parse comma command text into invoice items.

    Returns list of dicts: {sp, so_qc, qc_type, sl1pc, sl, price, note}
    """
    cleaned = text.replace(",", "").strip()
    price_list = get_customer_price_list(conn, kh_id) if kh_id else {}

    # Split by newlines, filter empty + "tao hd" lines
    lines = [l.strip() for l in cleaned.split("\n")]
    lines = [l for l in lines if l]
    while lines and lines[-1].lower().replace(" ", "") in ("taohd", "taohoadon"):
        lines.pop()

    invoice: list[dict] = []
    for line in lines:
        # Strip pattern suffix: <text>
        pattern_text = None
        clean_line = re.sub(r"<[^>]+>$", "", line).strip()
        if not clean_line:
            continue

        no_qc = _parse_no_qc(clean_line)
        if no_qc:
            sp = no_qc["sp"].upper()
            sl1qc_val = float(no_qc["sl1qc"])
            price_override = no_qc["price"]
            note = no_qc["note"]
            qc_type = None
            so_qc = [1]
        else:
            words = clean_line.split()
            if len(words) < 2:
                continue
            sp = words[0].upper()
            # Skip if first word doesn't look like a product code
            if not re.match(r'^[A-Z0-9][A-Z0-9.-]*$', sp):
                continue
            qc_raw = words[1]
            qc_type, so_qc = _parse_qc(qc_raw)
            if qc_type is not None:
                # Has QC: "KDDT 2t 50" → quantity is words[2]
                try:
                    sl1qc_val = float(words[2]) if len(words) > 2 else 0
                except (ValueError, TypeError):
                    continue
            else:
                # No QC: "KGL250 10" → qc_raw IS the quantity
                try:
                    sl1qc_val = float(qc_raw)
                except (ValueError, TypeError):
                    continue

            # Extract optional price override + note from remaining words
            if qc_type is not None:
                price_override = words[3] if len(words) > 3 else None
                note = " ".join(words[4:]) if len(words) > 4 else None
            else:
                price_override = words[2] if len(words) > 2 else None
                note = " ".join(words[3:]) if len(words) > 3 else None

        # Price: price list lookup, overridden by explicit price
        price = price_list.get(sp, 0)
        if price_override is not None:
            try:
                price = int(price_override)
            except ValueError:
                note = f"{price_override} {note or ''}".strip() or None

        sl = 1
        for v in so_qc:
            sl *= v
        sl *= int(sl1qc_val) if sl1qc_val else 0

        invoice.append({
            "sp": sp,
            "so_qc": so_qc,
            "qc_type": qc_type,
            "sl1pc": sl1qc_val,
            "sl": sl,
            "price": price,
            "note": note,
        })

    return invoice


def parse_invoice_free_text(conn, text: str, kh_id: str | int | None = None) -> list[dict]:
    """Parse free-form order text into invoice items by scanning for known product codes.

    Handles text like: "hoa ngà k2l 70 , k2nv128 50"
    Returns list of dicts: {sp, so_qc, qc_type, sl1pc, sl, price, note}
    """
    import re
    from product_db import get_all_products

    if not text or not text.strip():
        return []

    all_products = get_all_products(conn)
    valid_codes = {p["code"].upper() for p in all_products} if all_products else set()
    if not valid_codes:
        return []

    price_list = get_customer_price_list(conn, kh_id) if kh_id else {}

    # Normalize: commas/newlines → spaces, collapse whitespace
    cleaned = re.sub(r'[,\n]+', ' ', text)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    # Special: "dm180 1 lốc" / "dm180 1 loc" → "dm180 1b 12"
    cleaned = re.sub(r'(?i)(dm180)\s+1\s+l[ốo]c\b', r'\1 1b 12', cleaned)

    tokens = cleaned.split(' ')

    invoice = []
    i = 0
    while i < len(tokens):
        token_upper = tokens[i].upper()
        if token_upper in valid_codes:
            sp = token_upper
            i += 1
            if i >= len(tokens):
                i += 1
                continue

            next_token = tokens[i]
            qc_type = None
            so_qc = [1]
            sl1pc = 0
            has_qc = False

            # Check for QC format: <int>t, <int>b, <num>t<num>b
            m_t = re.match(r'^(\d+)t$', next_token)
            m_b = re.match(r'^(\d+)b$', next_token)
            m_tb = re.match(r'^([\d.]+)t([\d.]+)b$', next_token)
            if m_t:
                # e.g. 4t → 4 túi, default 50/túi
                qc_type = 't'
                so_qc = [int(m_t.group(1))]
                has_qc = True
                i += 1
            elif m_b:
                # e.g. 3b → 3 bịch, MUST have next number
                qc_type = 'b'
                so_qc = [int(m_b.group(1))]
                has_qc = True
                i += 1
            elif m_tb:
                # e.g. 2t3b → 2 túi x 3 bịch, default 50
                qc_type = 'tb'
                so_qc = [float(m_tb.group(1)), float(m_tb.group(2))]
                has_qc = True
                i += 1

            if has_qc:
                # Check for optional sl1pc after QC
                if qc_type == 't' or qc_type == 'tb':
                    sl1pc = 50  # default for túi
                    if i < len(tokens):
                        try:
                            sl1pc = int(tokens[i])
                            i += 1
                        except ValueError:
                            pass
                elif qc_type == 'b':
                    # bịch: if no explicit quantity follows, default 3
                    sl1pc = 3
                    if i < len(tokens):
                        try:
                            sl1pc = int(tokens[i])
                            i += 1
                        except ValueError:
                            pass  # keep default 3, don't consume token
            else:
                # No QC: plain number as sl1pc
                try:
                    sl1pc = int(next_token)
                    i += 1
                except ValueError:
                    continue

            sl = 1
            for v in so_qc:
                sl *= v
            sl *= sl1pc

            price = price_list.get(sp, 0)
            invoice.append({
                "sp": sp, "so_qc": so_qc, "qc_type": qc_type,
                "sl1pc": sl1pc, "sl": int(sl), "price": price, "note": None,
            })
            continue
        i += 1

    return invoice


def save_order_invoice(conn, thread_id: int, invoice: list[dict]) -> tuple[bool, str]:
    """Save parsed invoice items to an order. Returns (ok, message)."""
    data = get_order_by_thread_id(conn, thread_id)
    if data is None:
        return False, "Không tìm thấy đơn hàng"
    data["invoice"] = invoice
    data["updated_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    ok = _save_order(conn, thread_id, data)
    if ok:
        return True, f"✅ Đã lưu {len(invoice)} sản phẩm"
    return False, "❌ Lỗi lưu đơn hàng"


def detect_customer_free_text(conn, text: str) -> dict:
    """Detect customer from free-form order text using pattern matching.

    Scans all customers with patterns in SQLite, matches against order text.
    Returns: { matches: [{customerID, customerName, score, bestMatchedPattern}], autoAssign: {customerID, customerName, score} | None }
    """
    import re as _re
    from vn import vn_normalize

    if not text or not text.strip():
        return {"matches": [], "autoAssign": None}

    norm_text = vn_normalize(text)
    orig_text = text.lower()

    cur = conn.execute(
        "SELECT firebase_key, json FROM customers WHERE json_extract(json, '$.patterns') IS NOT NULL AND json_extract(json, '$.patterns') != '[]' AND deleted_at IS NULL"
    )
    candidates = []
    for row in cur.fetchall():
        cust = json.loads(row["json"])
        patterns = cust.get("patterns") or []
        if not patterns:
            continue
        best_pattern = None
        best_score = 0
        for pattern in patterns:
            p = (pattern or "").strip()
            if not p:
                continue
            norm_p = vn_normalize(p)
            word_re = _re.compile(r'(?:^|\s)' + _re.escape(norm_p) + r'(?:$|\s)', _re.IGNORECASE)
            if word_re.search(norm_text):
                score = len(norm_p) * 10
                if score > best_score:
                    best_score = score
                    best_pattern = p
            elif norm_p in norm_text:
                score = len(norm_p) * 3
                if score > best_score:
                    best_score = score
                    best_pattern = p

        if best_pattern:
            candidates.append({
                "customerID": row["firebase_key"],
                "customerName": cust.get("name", "N/A"),
                "score": best_score,
                "bestMatchedPattern": best_pattern,
            })

    candidates.sort(key=lambda c: c["score"], reverse=True)

    auto_assign = None
    # Auto-assign top match if score >= 30, or score >= 20 and no close runner-up
    if candidates and candidates[0]["score"] >= 20:
        if len(candidates) == 1:
            auto_assign = candidates[0]
        else:
            top = candidates[0]
            second = candidates[1]
            if top["score"] >= 30 or (top["score"] - second["score"] >= 15):
                auto_assign = top

    return {"matches": candidates, "autoAssign": auto_assign}
