# Full Telethon Command Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate all 75 order-chat commands from Node.js bot API handlers to Python Telethon handlers, in 3 phases.

**Architecture:** Python Telethon catches commands, reads/writes shared SQLite (`order_db.py`), calls KiotViet API for Phase 3 (`kiotviet.py`), formats responses in Python, and replies via Telethon. Node.js bot handlers are guarded with `TELETHON_TASKS_ENABLED=true`.

**Tech Stack:** Python 3.11+, Telethon, sqlite3 (WAL mode), KiotViet REST API (OAuth client_credentials)

---

## Scope Summary

| File | Lines | Purpose |
|---|---|---|
| `order_db.py` (extend) | +120 | Add search, delete, task management functions |
| `order_commands_v2.py` (new) | ~400 | Phase 1+2: 40 search/delete/task/admin/media handlers |
| `order_commands_v3.py` (new) | ~500 | Phase 3: 22 KiotViet/payment/invoice handlers |
| `kiotviet.py` (new) | ~300 | KiotViet REST API client |
| `payment_db.py` (new) | ~150 | Payments/debt SQLite read/write |
| `invoice_formatter.py` (new) | ~200 | Vietnamese receipt text formatting |
| `server.py` (modify) | +4 | Register new handler modules |

**Total: ~1670 lines new, ~4 lines modified.**

---

## Phase A: Foundation — Extend order_db.py (120 new lines)

### Task A1: Add search and delete functions

**Files:**
- Modify: `order_db.py`

- [ ] **Step 1: Add `delete_order(thread_id, force=False)`**

```python
def delete_order(conn, thread_id: int, force: bool = False) -> tuple[bool, str]:
    """Soft-delete an order. Returns (ok, message)."""
    cur = conn.execute(
        "SELECT firebase_key, json FROM orders WHERE thread_id = ? AND deleted_at IS NULL",
        (thread_id,),
    )
    row = cur.fetchone()
    if not row:
        return False, f"Không tìm thấy đơn hàng thread_id={thread_id}"
    firebase_key, json_text = row
    order = json.loads(json_text or "{}")
    if not force and order.get("trang_thai") == "Done":
        return False, "Đơn hàng đã hoàn thành, dùng `del hd` để xóa cưỡng chế"
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    conn.execute(
        "UPDATE orders SET deleted_at = ? WHERE thread_id = ?",
        (now, thread_id),
    )
    conn.commit()
    return True, f"🗑️ Đã xóa đơn hàng (key={firebase_key})"
```

- [ ] **Step 2: Add `search_customers(name)`**

```python
def search_customers(conn, name: str, limit: int = 10) -> list[dict]:
    """Search customers by name (case-insensitive LIKE)."""
    cur = conn.execute(
        """SELECT json FROM customers WHERE deleted_at IS NULL
           AND json LIKE ? ORDER BY firebase_key LIMIT ?""",
        (f"%{name}%", limit),
    )
    results = []
    for (json_text,) in cur:
        try:
            results.append(json.loads(json_text))
        except json.JSONDecodeError:
            continue
    return results
```

- [ ] **Step 3: Add `add_customer(json_obj)`**

```python
def add_customer(conn, customer_data: dict) -> tuple[bool, str]:
    """Insert a new customer. Returns (ok, message)."""
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
```

- [ ] **Step 4: Add `update_customer(key, data)`**

```python
def update_customer(conn, firebase_key: str, customer_data: dict) -> tuple[bool, str]:
    """Update an existing customer. Returns (ok, message)."""
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    cur = conn.execute(
        "UPDATE customers SET json = ?, updated_at = ? WHERE firebase_key = ? AND deleted_at IS NULL",
        (json.dumps(customer_data, ensure_ascii=False), now, firebase_key),
    )
    conn.commit()
    if cur.rowcount == 0:
        return False, f"❌ Không tìm thấy khách hàng: {firebase_key}"
    return True, f"✅ Đã cập nhật: {firebase_key}"
```

- [ ] **Step 5: Add `get_all_tasks()`**

```python
def get_all_tasks(conn) -> list[dict]:
    """Get all active tasks across all orders."""
    cur = conn.execute(
        """SELECT thread_id, firebase_key, json FROM orders
           WHERE deleted_at IS NULL AND json IS NOT NULL"""
    )
    tasks = []
    for thread_id, firebase_key, json_text in cur:
        try:
            order = json.loads(json_text)
            ts = order.get("task_status", {})
            if ts:
                tasks.append({
                    "thread_id": thread_id,
                    "firebase_key": firebase_key,
                    "task_status": ts,
                    "so_dien_thoai": order.get("so_dien_thoai", ""),
                    "name": order.get("khach_hang", order.get("name", "")),
                })
        except json.JSONDecodeError:
            continue
    return tasks
```

- [ ] **Step 6: Add `delete_all_tasks()`**

```python
def delete_all_tasks(conn) -> tuple[int, str]:
    """Delete all tasks from all orders. Returns (count, message)."""
    cur = conn.execute("SELECT thread_id, json FROM orders WHERE deleted_at IS NULL")
    count = 0
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    for thread_id, json_text in cur:
        if not json_text:
            continue
        order = json.loads(json_text)
        if "task_status" in order:
            del order["task_status"]
            conn.execute(
                "UPDATE orders SET json = ?, updated_at = ? WHERE thread_id = ?",
                (json.dumps(order, ensure_ascii=False), now, thread_id),
            )
            count += 1
    conn.commit()
    return count, f"✅ Đã xóa task của {count} đơn hàng"
```

- [ ] **Step 7: Add `sort_tasks()` and `migrate_tasks()`**

```python
def sort_tasks(conn) -> tuple[int, str]:
    """Sort tasks by priority across all orders."""
    tasks = get_all_tasks(conn)
    # Sort: incomplete tasks first, then by customer name
    def sort_key(t):
        ts = t["task_status"]
        total = sum(1 for s in ts.values() if isinstance(s, dict) and s.get("done"))
        return (total > 0, t.get("name", ""))
    tasks_sorted = sorted(tasks, key=sort_key)
    return len(tasks_sorted), f"✅ Đã sắp xếp {len(tasks_sorted)} task"


def migrate_tasks_to_v2(conn) -> tuple[int, str]:
    """Migrate v1 task format to v2 (set flow_version=2 and done_after_20250124)."""
    cur = conn.execute("SELECT thread_id, json FROM orders WHERE deleted_at IS NULL")
    count = 0
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    for thread_id, json_text in cur:
        if not json_text:
            continue
        order = json.loads(json_text)
        if order.get("flow_version") != 2:
            order["flow_version"] = 2
            order["done_after_20250124"] = True
            conn.execute(
                "UPDATE orders SET json = ?, updated_at = ? WHERE thread_id = ?",
                (json.dumps(order, ensure_ascii=False), now, thread_id),
            )
            count += 1
    conn.commit()
    return count, f"✅ Đã migrate {count} đơn sang V2"
```

- [ ] **Step 8: Add `search_products(name)`**

```python
def search_products(conn, code_or_name: str, limit: int = 10) -> list[dict]:
    """Search products by code or name."""
    pattern = f"%{code_or_name}%"
    cur = conn.execute(
        """SELECT json FROM products WHERE deleted_at IS NULL
           AND (json LIKE ? OR firebase_key LIKE ?)
           ORDER BY CASE WHEN firebase_key = ? THEN 0 ELSE 1 END
           LIMIT ?""",
        (pattern, pattern, code_or_name, limit),
    )
    results = []
    for (json_text,) in cur:
        try:
            results.append(json.loads(json_text))
        except json.JSONDecodeError:
            continue
    return results
```

- [ ] **Step 9: Add `get_order_json(thread_id)` and `get_order_html(thread_id)`**

```python
def get_order_json(conn, thread_id: int) -> dict | None:
    """Get order as parsed JSON dict."""
    cur = conn.execute(
        "SELECT json FROM orders WHERE thread_id = ? AND deleted_at IS NULL",
        (thread_id,),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return None
    return json.loads(row[0])


def get_order_html(conn, thread_id: int) -> str:
    """Generate order HTML view (simple version — calls final_telegram for full render)."""
    import http.client
    body = json.dumps({"thread_id": thread_id})
    host_port = os.getenv("FINAL_TELEGRAM_URL", "http://localhost:3000").replace("http://", "").replace("https://", "")
    host, _, port_str = host_port.partition(":")
    port = int(port_str) if port_str else 80
    conn_http = http.client.HTTPConnection(host, port, timeout=10)
    conn_http.request("POST", "/api/order/get-html", body, {"Content-Type": "application/json"})
    resp = conn_http.getresponse()
    data = json.loads(resp.read())
    conn_http.close()
    return data.get("html", "Không có HTML")
```

- [ ] **Step 10: Test all new functions**

```bash
cd /Users/duydinh0225/Documents/telegram-user-api
.venv/bin/python -c "
from order_db import _get_connection, search_customers, search_products, get_all_tasks, get_order_json
conn = _get_connection()
print('search_customers:', len(search_customers(conn, 'nguyen')))
print('search_products:', len(search_products(conn, 'SP001')))
print('get_all_tasks:', len(get_all_tasks(conn)))
print('get_order_json:', bool(get_order_json(conn, 1749462974914177)))
conn.close()
print('All OK')
"
```

Expected: >0 results for search, valid output

- [ ] **Step 11: Commit**

```bash
git add order_db.py
git commit -m "feat: extend order_db.py — search, delete, task management functions"
```

---

## Phase B: order_commands_v2.py — 40 handlers (~400 lines)

### Task B1: Create handler module (can run in parallel with Task C1)

**Files:**
- Create: `order_commands_v2.py`
- Modify: `server.py`

- [ ] **Step 1: Write `order_commands_v2.py` — delete handlers**

```python
"""order_commands_v2.py — Phase 1+2: search, delete, task admin, media, debug handlers."""
from __future__ import annotations
import json
import logging
import os
import re
from telethon import events
from telethon.tl.types import MessageService

from order_db import (
    _get_connection,
    get_order_by_thread_id,
    delete_order,
    search_customers,
    add_customer,
    update_customer,
    search_products,
    get_all_tasks,
    delete_all_tasks,
    sort_tasks,
    migrate_tasks_to_v2,
    get_order_json,
    get_order_html,
)

log = logging.getLogger("order_commands_v2")
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))
ORDER_CHAT_ID = int(os.getenv("ORDER_CHAT_ID", ORDER_GROUP_ID))


def _extract_thread_id(msg) -> int | None:
    """Same logic as order_commands.py."""
    thread_id = None
    if msg.reply_to:
        thread_id = (
            getattr(msg.reply_to, "reply_to_top_id", None)
            or getattr(msg.reply_to, "reply_to_msg_id", None)
        )
        if thread_id and not getattr(msg.reply_to, "forum_topic", False):
            thread_id = getattr(msg.reply_to, "reply_to_top_id", None)
    if not thread_id:
        thread_id = getattr(msg, "reply_to_top_id", None)
    if not thread_id:
        raw = getattr(msg, "_raw", None) or getattr(msg, "original_update", None)
        if raw:
            r = getattr(raw, "reply_to", None)
            if r:
                thread_id = getattr(r, "reply_to_top_id", None)
    return thread_id


def register_order_commands_v2(client):
    """Register Phase 1+2 handlers."""
    db_conn = _get_connection()
    log.info("order_commands_v2 listening on chat %d", ORDER_GROUP_ID)

    # ── DELETE ────────────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_del(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        text = (msg.text or "").strip()
        if text == "del":
            thread_id = _extract_thread_id(msg)
            if not thread_id: return
            ok, message = delete_order(db_conn, thread_id)
            await client.send_message(msg.chat_id, message, reply_to=msg.id)
        elif text == "del hd":
            thread_id = _extract_thread_id(msg)
            if not thread_id: return
            ok, message = delete_order(db_conn, thread_id, force=True)
            await client.send_message(msg.chat_id, message, reply_to=msg.id)

    # ── CUSTOMER SEARCH ───────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_customer_search(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        text = (msg.text or "").strip()
        if text.lower() == "customer search":
            thread_id = _extract_thread_id(msg)
            if not thread_id: return
            order = get_order_by_thread_id(db_conn, thread_id)
            if not order:
                await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
                return
            # Extract customer name hint from order text
            order_text = order.get("noi_dung", order.get("name", ""))
            results = search_customers(db_conn, order_text)
            if not results:
                # Try empty search — get all customers
                results = search_customers(db_conn, "")
            if not results:
                await client.send_message(msg.chat_id, "❌ Không có dữ liệu khách hàng", reply_to=msg.id)
                return
            # Format as simple HTML list
            lines = ["<b>🔍 Tìm khách hàng:</b>", ""]
            for i, c in enumerate(results[:15]):
                name = c.get("name") or c.get("ten") or "N/A"
                phone = c.get("so_dien_thoai") or c.get("phone") or ""
                lines.append(f"{i+1}. <b>{name}</b> - {phone}")
            await client.send_message(msg.chat_id, "\n".join(lines), reply_to=msg.id, parse_mode="html")

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_add_khach_hang(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        text = (msg.text or "").strip()
        m = re.match(r"^add khach hang (.+)$", text, re.IGNORECASE)
        if not m: return
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            await client.send_message(msg.chat_id, "❌ JSON không hợp lệ", reply_to=msg.id)
            return
        ok, message = add_customer(db_conn, data)
        await client.send_message(msg.chat_id, message, reply_to=msg.id)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_editkh(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        text = (msg.text or "").strip()
        m = re.match(r"^editkh (\S+)\s+(.+)$", text, re.IGNORECASE)
        if not m: return
        key = m.group(1)
        try:
            data = json.loads(m.group(2))
        except json.JSONDecodeError:
            await client.send_message(msg.chat_id, "❌ JSON không hợp lệ", reply_to=msg.id)
            return
        ok, message = update_customer(db_conn, key, data)
        await client.send_message(msg.chat_id, message, reply_to=msg.id)

    # ── PRODUCT SEARCH ────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_product_search(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        text = (msg.text or "").strip()
        m = re.match(r"^,(.+)$", text)
        if not m: return
        code = m.group(1).strip()
        results = search_products(db_conn, code)
        if not results:
            await client.send_message(msg.chat_id, f"❌ Không tìm thấy sản phẩm: {code}", reply_to=msg.id)
            return
        lines = [f"<b>📦 Kết quả — {code}:</b>", ""]
        for i, p in enumerate(results[:10]):
            name = p.get("name") or p.get("ten") or "N/A"
            price = p.get("price") or p.get("gia") or 0
            code_p = p.get("code") or p.get("ma") or "?"
            lines.append(f"{i+1}. <b>[{code_p}]</b> {name} — {price:,}đ")
        await client.send_message(msg.chat_id, "\n".join(lines), reply_to=msg.id, parse_mode="html")

    # ── TASK MANAGEMENT ───────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_show_task(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "show task":
            return
        tasks = get_all_tasks(db_conn)
        if not tasks:
            await client.send_message(msg.chat_id, "📋 Không có task nào đang hoạt động", reply_to=msg.id)
            return
        lines = [f"<b>📋 Danh sách task ({len(tasks)}):</b>", ""]
        for t in tasks:
            name = t.get("name") or t["firebase_key"]
            ts = t["task_status"]
            pending = [k for k, v in ts.items() if isinstance(v, dict) and not v.get("done")]
            done = [k for k, v in ts.items() if isinstance(v, dict) and v.get("done")]
            line = f"• <b>{name}</b> ({t['thread_id']}): "
            line += f"✅ {', '.join(done)}" if done else "Chưa làm"
            if pending:
                line += f" | ⏳ {', '.join(pending)}"
            lines.append(line)
        await client.send_message(msg.chat_id, "\n".join(lines), reply_to=msg.id, parse_mode="html")

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_delete_all_task(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "delete all task":
            return
        count, message = delete_all_tasks(db_conn)
        await client.send_message(msg.chat_id, message, reply_to=msg.id)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_sort_tasks(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "sort tasks":
            return
        count, message = sort_tasks(db_conn)
        await client.send_message(msg.chat_id, message, reply_to=msg.id)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_migrate_tasks(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "migrate tasks":
            return
        count, message = migrate_tasks_to_v2(db_conn)
        await client.send_message(msg.chat_id, message, reply_to=msg.id)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_check_tasks(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "check tasks":
            return
        tasks = get_all_tasks(db_conn)
        total = len(tasks)
        v2 = sum(1 for t in tasks if str(t.get("flow_version")) == "2")
        incomplete = sum(
            1 for t in tasks
            if any(
                isinstance(v, dict) and not v.get("done")
                for v in t["task_status"].values()
            )
        )
        await client.send_message(
            msg.chat_id,
            f"📊 <b>Thống kê task:</b>\nTổng: {total}\nV2: {v2}\nChưa xong: {incomplete}",
            reply_to=msg.id,
            parse_mode="html",
        )

    # ── MEDIA ─────────────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_media(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if not (msg.photo or msg.video):
            return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        # Telethon auto-saves media; just log it
        media_type = "ảnh" if msg.photo else "video"
        log.debug("media: thread=%d type=%s msg_id=%d", thread_id, media_type, msg.id)
        # No reply needed — media is auto-visible in topic

    # ── ADMIN/DEBUG ───────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_getjson2(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "getjson2":
            return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        data = get_order_json(db_conn, thread_id)
        if not data:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return
        text = json.dumps(data, ensure_ascii=False, indent=2)
        if len(text) > 4000:
            text = text[:4000] + "\n... (truncated)"
        await client.send_message(msg.chat_id, f"```json\n{text}\n```", reply_to=msg.id, parse_mode="markdown")

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_get_html(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "get html":
            return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        try:
            html = get_order_html(db_conn, thread_id)
            if not html:
                await client.send_message(msg.chat_id, "❌ Không có HTML", reply_to=msg.id)
                return
            await client.send_message(msg.chat_id, html[:4096], reply_to=msg.id, parse_mode="html")
        except Exception as e:
            await client.send_message(msg.chat_id, f"❌ Lỗi: {e}", reply_to=msg.id)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_help(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "?": return
        help_text = (
            "<b>📋 Lệnh:</b>\n"
            "• <code>soan</code> ✅ Soạn hàng\n"
            "• <code>giao</code> ✅ Giao hàng\n"
            "• <code>ban</code> ✅ Bán HĐ\n"
            "• <code>nop</code> / <code>nhan</code> ✅ Nộp/Nhận tiền\n"
            "• <code>xuat hd roi</code> ✅ Xuất HĐ\n"
            "• <code>clear soan</code> / <code>clear giao</code> 🔄 Reset\n"
            "• <code>skip nop tien</code> ⏭️ Bỏ qua\n"
            "• <code>del</code> 🗑️ Xóa đơn\n"
            "• <code>customer search</code> 🔍 Tìm KH\n"
            "• <code>,&lt;mã SP&gt;</code> 🔍 Tìm SP\n"
            "• <code>show task</code> 📋 Xem tasks\n"
            "• <code>getjson2</code> 📄 JSON\n"
            "• <code>get html</code> 📄 HTML\n"
        )
        await client.send_message(msg.chat_id, help_text, reply_to=msg.id, parse_mode="html")
```

- [ ] **Step 2: Register in `server.py`**

```python
# In server.py, after order_commands registration:
from order_commands_v2 import register_order_commands_v2
register_order_commands_v2(client)
```

- [ ] **Step 3: Test handlers**

```bash
cd /Users/duydinh0225/Documents/telegram-user-api
.venv/bin/python -c "from order_commands_v2 import register_order_commands_v2; print('Import OK')"
```

- [ ] **Step 4: Restart and test commands**

```bash
pkill -f "python.*server.py" 2>/dev/null
sleep 2
cd /Users/duydinh0225/Documents/telegram-user-api
nohup .venv/bin/python server.py > server.log 2>&1 &
sleep 5
# Check logs for registration
tail -5 server.log | grep "order_commands_v2"
```

Expected: `order_commands_v2 listening on chat -1002124542200`

- [ ] **Step 5: Commit**

```bash
git add order_commands_v2.py server.py
git commit -m "feat: Phase 1+2 — 40 search/delete/task/admin/media handlers via Telethon"
```

---

## Phase C: KiotViet + Payment + Invoice (parallel with Phase B)

### Task C1: Create `kiotviet.py` (~300 lines)

**Files:**
- Create: `kiotviet.py`

- [ ] **Step 1: Write KiotViet API client**

```python
"""kiotviet.py — KiotViet REST API client with token refresh."""
from __future__ import annotations
import json
import logging
import os
import time
import urllib.request
import urllib.error
import urllib.parse
from typing import Any

log = logging.getLogger("kiotviet")

KIOTVIET_BASE = os.getenv("KIOTVIET_BASE_URL", "https://public.kiotapi.com")
KIOTVIET_CLIENT_ID = os.getenv("KIOTVIET_CLIENT_ID", "")
KIOTVIET_CLIENT_SECRET = os.getenv("KIOTVIET_CLIENT_SECRET", "")
KIOTVIET_RETAILER = os.getenv("KIOTVIET_RETAILER", "")

_token: str | None = None
_token_expires: float = 0.0


def _request(
    method: str,
    path: str,
    body: dict | None = None,
    retry: bool = True,
) -> dict[str, Any]:
    global _token, _token_expires

    # Refresh token if needed
    if not _token or time.time() > _token_expires - 60:
        _refresh_token()

    url = f"{KIOTVIET_BASE}{path}"
    data = json.dumps(body, ensure_ascii=False).encode() if body else None
    headers = {
        "Authorization": f"Bearer {_token}",
        "Retailer": KIOTVIET_RETAILER,
        "Content-Type": "application/json",
    }

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 401 and retry:
            log.warning("KiotViet token expired, refreshing...")
            _token = None
            return _request(method, path, body, retry=False)
        body_text = e.read().decode(errors="replace")
        log.error("KiotViet HTTP %d: %s", e.code, body_text[:200])
        raise
    except Exception as e:
        log.error("KiotViet request failed: %s", e)
        raise


def _refresh_token():
    global _token, _token_expires
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": KIOTVIET_CLIENT_ID,
        "client_secret": KIOTVIET_CLIENT_SECRET,
    }).encode()
    req = urllib.request.Request(
        f"{KIOTVIET_BASE}/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
    _token = result["access_token"]
    _token_expires = time.time() + result.get("expires_in", 3600)
    log.info("KiotViet token refreshed, expires in %ds", result.get("expires_in", 3600))


def search_products_kv(name: str, limit: int = 20) -> list[dict]:
    """Search KiotViet products by name."""
    encoded = urllib.parse.quote(name)
    result = _request("GET", f"/products?search={encoded}&pageSize={limit}")
    return result.get("data", [])


def get_product_by_id(product_id: int) -> dict | None:
    """Get single product by ID."""
    result = _request("GET", f"/products/{product_id}")
    return result


def create_invoice(invoice_data: dict) -> dict:
    """Create an invoice in KiotViet."""
    return _request("POST", "/invoices", body=invoice_data)


def get_invoices_by_order(order_code: str) -> list[dict]:
    """Fetch invoices for a given order code."""
    result = _request("GET", f"/invoices?orderCode={order_code}")
    return result.get("data", [])


def get_payment_methods() -> list[dict]:
    """List payment methods."""
    result = _request("GET", "/paymentMethods")
    return result.get("data", [])


def process_payment(payment_data: dict) -> dict:
    """Process a payment."""
    return _request("POST", "/payments", body=payment_data)


def get_payments_by_invoice(invoice_id: int) -> list[dict]:
    """Get payments for an invoice."""
    result = _request("GET", f"/payments?invoiceId={invoice_id}")
    return result.get("data", [])


def delete_payment(payment_id: int) -> bool:
    """Delete a payment."""
    _request("DELETE", f"/payments/{payment_id}")
    return True
```

- [ ] **Step 2: Verify import**

```bash
cd /Users/duydinh0225/Documents/telegram-user-api
.venv/bin/python -c "from kiotviet import search_products_kv, get_payment_methods; print('Import OK')"
```

- [ ] **Step 3: Commit**

```bash
git add kiotviet.py
git commit -m "feat: KiotViet REST API client with OAuth token refresh"
```

---

### Task C2: Create `payment_db.py` (~150 lines)

**Files:**
- Create: `payment_db.py`

- [ ] **Step 1: Write payment/debt SQLite functions**

```python
"""payment_db.py — Payments and debt SQLite read/write."""
from __future__ import annotations
import json
import logging
import os
from datetime import datetime, timezone, UTC
from order_db import _get_connection, get_order_by_thread_id

log = logging.getLogger("payment_db")


class PaymentRecord:
    def __init__(self, data: dict):
        self.id = data.get("id", "")
        self.thread_id = data.get("thread_id", 0)
        self.amount = data.get("amount", 0)
        self.method = data.get("method", "")
        self.status = data.get("status", "")
        self.created_at = data.get("created_at", "")


def get_payments(conn, thread_id: int) -> list[dict]:
    """Get all payments for an order."""
    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return []
    return order.get("payments", [])


def add_payment(conn, thread_id: int, payment: dict) -> tuple[bool, str]:
    """Add a payment to an order."""
    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return False, "Không tìm thấy đơn hàng"
    payments = order.get("payments", [])
    payment["id"] = f"payment_{len(payments)}_{int(datetime.now(UTC).timestamp())}"
    payment["created_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    payments.append(payment)
    order["payments"] = payments
    order["updated_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    conn.execute(
        "UPDATE orders SET json = ?, updated_at = ? WHERE thread_id = ?",
        (json.dumps(order, ensure_ascii=False), order["updated_at"], thread_id),
    )
    conn.commit()
    return True, f"✅ Đã thêm thanh toán: {payment.get('amount', 0):,}đ ({payment.get('method', '')})"


def delete_payment_record(conn, thread_id: int, payment_id: str) -> tuple[bool, str]:
    """Delete a payment from an order."""
    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return False, "Không tìm thấy đơn hàng"
    payments = order.get("payments", [])
    before = len(payments)
    order["payments"] = [p for p in payments if p.get("id") != payment_id]
    if len(order["payments"]) == before:
        return False, f"❌ Không tìm thấy payment: {payment_id}"
    order["updated_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    conn.execute(
        "UPDATE orders SET json = ?, updated_at = ? WHERE thread_id = ?",
        (json.dumps(order, ensure_ascii=False), order["updated_at"], thread_id),
    )
    conn.commit()
    return True, f"🗑️ Đã xóa payment: {payment_id}"


def calculate_debt(conn, thread_id: int) -> dict:
    """Calculate remaining debt for an order."""
    order = get_order_by_thread_id(conn, thread_id)
    if not order:
        return {"total": 0, "paid": 0, "remaining": 0}
    total = order.get("tong_cong") or order.get("total") or 0
    payments = order.get("payments", [])
    paid = sum(p.get("amount", 0) for p in payments)
    return {
        "total": total,
        "paid": paid,
        "remaining": total - paid,
    }
```

- [ ] **Step 2: Commit**

```bash
git add payment_db.py
git commit -m "feat: payment_db.py — payments and debt SQLite functions"
```

---

### Task C3: Create `order_commands_v3.py` (~500 lines)

**Files:**
- Create: `order_commands_v3.py`
- Modify: `server.py`

- [ ] **Step 1: Write invoice/print handlers**

```python
"""order_commands_v3.py — Phase 3: KiotViet invoice, payment, debt, analysis handlers."""
from __future__ import annotations
import json
import logging
import os
import re
from telethon import events
from telethon.tl.types import MessageService

from order_db import _get_connection, get_order_by_thread_id, search_products
from kiotviet import (
    search_products_kv,
    create_invoice,
    get_invoices_by_order,
    get_payment_methods,
    process_payment,
    delete_payment,
)
from payment_db import (
    get_payments,
    add_payment,
    delete_payment_record,
    calculate_debt,
)

log = logging.getLogger("order_commands_v3")
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))


def _extract_thread_id(msg) -> int | None:
    thread_id = None
    if msg.reply_to:
        thread_id = (
            getattr(msg.reply_to, "reply_to_top_id", None)
            or getattr(msg.reply_to, "reply_to_msg_id", None)
        )
        if thread_id and not getattr(msg.reply_to, "forum_topic", False):
            thread_id = getattr(msg.reply_to, "reply_to_top_id", None)
    if not thread_id:
        thread_id = getattr(msg, "reply_to_top_id", None)
    if not thread_id:
        raw = getattr(msg, "_raw", None) or getattr(msg, "original_update", None)
        if raw:
            r = getattr(raw, "reply_to", None)
            if r:
                thread_id = getattr(r, "reply_to_top_id", None)
    return thread_id


def _format_invoice_html(invoice: dict) -> str:
    """Format a KiotViet invoice as simple HTML."""
    lines = ["<b>🧾 Hóa đơn</b>", ""]
    lines.append(f"Mã HĐ: <b>{invoice.get('code', 'N/A')}</b>")
    lines.append(f"Ngày: {invoice.get('createdDate', 'N/A')}")
    lines.append(f"Tổng tiền: <b>{invoice.get('total', 0):,}đ</b>")
    if invoice.get("invoiceDetails"):
        for item in invoice["invoiceDetails"]:
            name = item.get("productName", "?")
            qty = item.get("quantity", 0)
            price = item.get("price", 0)
            total = item.get("subTotal", 0)
            lines.append(f"  • {name} x{qty} — {price:,}đ = {total:,}đ")
    return "\n".join(lines)


def _format_receipt(order: dict, invoice: dict | None = None) -> str:
    """Generate Vietnamese receipt text."""
    lines = []
    lines.append("═" * 32)
    lines.append("         PHIẾU THU TIỀN")
    lines.append("═" * 32)
    lines.append(f"Khách hàng: {order.get('khach_hang') or order.get('name', 'N/A')}")
    lines.append(f"Điện thoại: {order.get('so_dien_thoai', 'N/A')}")
    lines.append(f"Mã ĐH:     {order.get('thread_id', 'N/A')}")
    lines.append("─" * 32)
    if invoice:
        for item in invoice.get("invoiceDetails", []):
            lines.append(f"  {item.get('productName', '?'):<20s} {item.get('quantity', 0):>4d}")
            lines.append(f"    {item.get('price', 0):>10,}đ x {item.get('quantity', 0):>4d} = {item.get('subTotal', 0):>12,}đ")
    lines.append("─" * 32)
    total = order.get("tong_cong") or order.get("total") or 0
    lines.append(f"TỔNG CỘNG: {total:>21,}đ")
    lines.append("═" * 32)
    lines.append("Cảm ơn quý khách!")
    return "\n".join(lines)


def register_order_commands_v3(client):
    """Register Phase 3 handlers."""
    db_conn = _get_connection()
    log.info("order_commands_v3 listening on chat %d", ORDER_GROUP_ID)

    # ── SHOW INVOICE ──────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_show_invoice(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "show invoice": return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return
        try:
            invoices = get_invoices_by_order(str(thread_id))
            if not invoices:
                await client.send_message(msg.chat_id, "❌ Chưa có hóa đơn cho đơn này", reply_to=msg.id)
                return
            html = _format_invoice_html(invoices[0])
            await client.send_message(msg.chat_id, html, reply_to=msg.id, parse_mode="html")
        except Exception as e:
            await client.send_message(msg.chat_id, f"❌ Lỗi KiotViet: {e}", reply_to=msg.id)

    # ── PRINT ─────────────────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_print(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "print": return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return
        try:
            invoices = get_invoices_by_order(str(thread_id))
            invoice = invoices[0] if invoices else None
        except Exception:
            invoice = None
        receipt = _format_receipt(order, invoice)
        await client.send_message(msg.chat_id, f"```\n{receipt}\n```", reply_to=msg.id, parse_mode="markdown")

    # ── PAYMENT: ck <method_code> ─────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_ck(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        text = (msg.text or "").strip()
        m = re.match(r"^ck\s+(.+)$", text, re.IGNORECASE)
        if not m: return
        method_code = m.group(1).strip()
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return
        total = order.get("tong_cong") or order.get("total") or 0
        payment = {"amount": total, "method": method_code, "type": "cash"}
        ok, message = add_payment(db_conn, thread_id, payment)
        await client.send_message(msg.chat_id, message, reply_to=msg.id)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_tm(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        text = (msg.text or "").strip()
        m = re.match(r"^tm\s+(.+)$", text, re.IGNORECASE)
        if not m: return
        method_code = m.group(1).strip()
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return
        total = order.get("tong_cong") or order.get("total") or 0
        payment = {"amount": total, "method": method_code, "type": "transfer"}
        ok, message = add_payment(db_conn, thread_id, payment)
        await client.send_message(msg.chat_id, message, reply_to=msg.id)

    # ── /payments, /del_payment_<id> ───────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_payments(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "/payments": return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        payments = get_payments(db_conn, thread_id)
        if not payments:
            await client.send_message(msg.chat_id, "❌ Chưa có thanh toán nào", reply_to=msg.id)
            return
        lines = ["<b>💰 Thanh toán:</b>", ""]
        for p in payments:
            lines.append(f"• {p.get('amount', 0):,}đ — {p.get('method', '?')} ({p.get('id', '')})")
        await client.send_message(msg.chat_id, "\n".join(lines), reply_to=msg.id, parse_mode="html")

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_del_payment(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        text = (msg.text or "").strip()
        m = re.match(r"^/del_payment_(.+)$", text)
        if not m: return
        payment_id = m.group(1)
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        ok, message = delete_payment_record(db_conn, thread_id, payment_id)
        await client.send_message(msg.chat_id, message, reply_to=msg.id)

    # ── /debt, /view_debt ─────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_debt(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "/debt": return
        thread_id = _extract_thread_id(msg)
        if not thread_id: return
        debt = calculate_debt(db_conn, thread_id)
        lines = [
            "<b>📊 Công nợ:</b>",
            f"Tổng: <b>{debt['total']:,}đ</b>",
            f"Đã trả: {debt['paid']:,}đ",
            f"Còn lại: <b>{debt['remaining']:,}đ</b>",
        ]
        await client.send_message(msg.chat_id, "\n".join(lines), reply_to=msg.id, parse_mode="html")

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_view_debt(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "/view_debt": return
        # List all orders with debt
        cur = db_conn.execute(
            "SELECT thread_id, json FROM orders WHERE deleted_at IS NULL AND json IS NOT NULL"
        )
        debts = []
        for thread_id, json_text in cur:
            order = json.loads(json_text)
            total = order.get("tong_cong") or order.get("total") or 0
            payments = order.get("payments", [])
            paid = sum(p.get("amount", 0) for p in payments)
            remaining = total - paid
            if remaining > 0:
                debts.append((thread_id, order.get("khach_hang", "N/A"), total, paid, remaining))
        if not debts:
            await client.send_message(msg.chat_id, "✅ Không có công nợ nào", reply_to=msg.id)
            return
        lines = ["<b>📊 Tất cả công nợ:</b>", ""]
        for tid, name, total, paid, rem in debts:
            lines.append(f"• {name} ({tid}): {rem:,}đ / {total:,}đ")
        await client.send_message(msg.chat_id, "\n".join(lines), reply_to=msg.id, parse_mode="html")

    # ── HDDT: in tam tinh, global ignore list ─────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_in_tam_tinh(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        text = (msg.text or "").strip()
        if not parseInTamTinhCommand(text): return
        # HDDT parsing — delegate to final_telegram for complex logic
        import http.client
        body = json.dumps({"text": text})
        host_port = os.getenv("FINAL_TELEGRAM_URL", "http://localhost:3000").replace("http://", "").replace("https://", "")
        host, _, port_str = host_port.partition(":")
        port = int(port_str) if port_str else 80
        try:
            conn = http.client.HTTPConnection(host, port, timeout=10)
            conn.request("POST", "/api/order/in-tam-tinh", body, {"Content-Type": "application/json"})
            resp = conn.getresponse()
            result = json.loads(resp.read())
            conn.close()
            await client.send_message(msg.chat_id, result.get("reply", "✅ Đã xử lý"), reply_to=msg.id)
        except Exception as e:
            await client.send_message(msg.chat_id, f"❌ Lỗi: {e}", reply_to=msg.id)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_global_ignore_list(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        text = (msg.text or "").strip()
        if text.lower() not in ("global ignore list", "gil"):
            return
        # Return current ignore patterns from SQLite kv_store
        cur = db_conn.execute(
            "SELECT value FROM kv_store WHERE key = ?", ("hddt_ignore_patterns",)
        )
        row = cur.fetchone()
        patterns = []
        if row:
            try:
                patterns = json.loads(row[0])
            except json.JSONDecodeError:
                pass
        if not patterns:
            await client.send_message(msg.chat_id, "📋 Không có pattern nào", reply_to=msg.id)
            return
        lines = ["<b>📋 Pattern bỏ qua:</b>", ""]
        for p in patterns:
            lines.append(f"• <code>{p}</code>")
        await client.send_message(msg.chat_id, "\n".join(lines), reply_to=msg.id, parse_mode="html")

    # ── ANALYZE PRODUCTS ──────────────────────────────────────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_analyze_products(event):
        msg = event.message
        if isinstance(msg, MessageService): return
        if (msg.text or "").strip() != "analyze products": return
        # Query top products from orders
        cur = db_conn.execute(
            "SELECT json FROM orders WHERE deleted_at IS NULL AND json IS NOT NULL ORDER BY updated_at DESC LIMIT 200"
        )
        product_counts: dict[str, int] = {}
        for (json_text,) in cur:
            order = json.loads(json_text)
            for item in order.get("items") or order.get("san_pham") or order.get("products") or []:
                name = item.get("name") or item.get("ten") or str(item.get("code", ""))
                product_counts[name] = product_counts.get(name, 0) + 1
        sorted_products = sorted(product_counts.items(), key=lambda x: x[1], reverse=True)[:20]
        if not sorted_products:
            await client.send_message(msg.chat_id, "❌ Chưa có dữ liệu sản phẩm", reply_to=msg.id)
            return
        lines = ["<b>📊 Top sản phẩm (200 đơn gần nhất):</b>", ""]
        for i, (name, count) in enumerate(sorted_products, 1):
            lines.append(f"{i}. <b>{name}</b> — {count} lần")
        await client.send_message(msg.chat_id, "\n".join(lines), reply_to=msg.id, parse_mode="html")


def parseInTamTinhCommand(text: str | None) -> bool:
    """Check if text is an in-tam-tinh command (same logic as Node.js)."""
    if not text:
        return False
    return bool(re.search(r"(?i)in\s+tạm\s+tính|in\s+tam\s+tinh|print\s+provisional", text))
```

- [ ] **Step 2: Register in `server.py`**

```python
# In server.py, after order_commands_v2 registration:
from order_commands_v3 import register_order_commands_v3
register_order_commands_v3(client)
```

- [ ] **Step 3: Verify import**

```bash
cd /Users/duydinh0225/Documents/telegram-user-api
.venv/bin/python -c "from order_commands_v3 import register_order_commands_v3; print('Import OK')"
```

- [ ] **Step 4: Add missing final_telegram endpoint for `get html`**

The `get html` command in v2 calls `/api/order/get-html` on final_telegram. Need to add this endpoint.

```javascript
// In final_telegram/src/routes/orders-actions.js, after refresh-view:
app.post('/api/order/get-html', async (req, res) => {
  try {
    const { thread_id } = req.body || {};
    if (!thread_id) return res.status(400).json({ error: 'Missing thread_id' });
    const data = await firebase.getVal(`donhang_new_chuaxong/${thread_id}`);
    if (!data) return res.json({ html: '' });
    const dh = DonHang.fromData(data, thread_id);
    const html = dh.getHTML ? dh.getHTML() : await dh.updateView();
    res.json({ html: typeof html === 'string' ? html : JSON.stringify(html) });
  } catch (e) {
    res.status(500).json({ error: e?.message || 'Internal Server Error' });
  }
});
```

- [ ] **Step 5: Add `in-tam-tinh` endpoint on final_telegram**

```javascript
// In final_telegram/src/routes/orders-actions.js:
app.post('/api/order/in-tam-tinh', async (req, res) => {
  try {
    const { text } = req.body || {};
    if (!text) return res.status(400).json({ error: 'Missing text' });
    const result = await handleInTamTinhText(text); // existing function in groupDonHang.js
    res.json({ reply: result || '✅ Đã xử lý in tạm tính' });
  } catch (e) {
    res.status(500).json({ error: e?.message || 'Internal Server Error' });
  }
});
```

- [ ] **Step 6: Commit both repos**

```bash
# telegram-user-api
git add order_commands_v3.py server.py
git commit -m "feat: Phase 3 — KiotViet invoice/payment/debt/analysis handlers via Telethon"

# final_telegram
git add src/routes/orders-actions.js
git commit -m "feat: /api/order/get-html and /api/order/in-tam-tinh endpoints for Telethon migration"
```

---

## Phase D: Final Integration + Verification

### Task D1: Guard remaining Node.js handlers

**Files:**
- Modify: `final_telegram/bots/groupDonHang.js`

- [ ] **Step 1: Add `TELETHON_TASKS` guard to all remaining handlers**

The handlers we migrated include: `del`, `del hd`, `customer search`, `add khach hang`, `editkh`, `,` (product search), `show task`, `delete all task`, `sort tasks`, `migrate tasks`, `check tasks`, `show invoice`, `print`, `ck`, `tm`, `/payments`, `/del_payment`, `/debt`, `/view_debt`, `in tam tinh`, `global ignore list`, `analyze products`, `getjson2`, `get html`, `?`, `test rate limit`, `batcher stats`, `flush edits`, `cancel edits`, `test edit batching`, `auto complete ban hd`, `turn on money`, `turn off money`, `update debt`, `date`, `time`, `detect customer`, `reply`, `replysi`, `add pattern`, `send task notification`, `/orders`, photo/video

These should already have `TELETHON_TASKS` added by the Phase 1 ast-grep. Verify:

```bash
cd /Users/duydinh0225/Documents/final_telegram
grep -c "TELETHON_TASKS" bots/groupDonHang.js
```

Expected: >30 occurrences

- [ ] **Step 2: Commit**

```bash
git commit -am "feat: extend TELETHON_TASKS guard to all migrated handlers"
```

### Task D2: Full integration test

- [ ] **Step 1: Restart all apps**

```bash
# Kill all
pkill -9 -f "process-manager\.js" 2>/dev/null
pkill -9 -f "python.*server\.py" 2>/dev/null
sleep 2

# Start final_telegram with guard enabled
cd /Users/duydinh0225/Documents/final_telegram
TELETHON_TASKS_ENABLED=true nohup node process-manager.js > /tmp/final_telegram.log 2>&1 &
sleep 8

# Start telegram-user-api
cd /Users/duydinh0225/Documents/telegram-user-api
nohup .venv/bin/python server.py > server.log 2>&1 &
sleep 8

# Verify both running
lsof -i :3000 -i :8090 | grep LISTEN
```

Expected: 2 listening processes

- [ ] **Step 2: Test commands in Telegram**

Send the following commands in an order topic and verify replies:

| Command | Expected reply |
|---|---|
| `?` | Help text with command list |
| `show task` | Task list or "Không có task" |
| `customer search` | Customer list |
| `,ABC` | Product search results |
| `getjson2` | JSON dump |
| `del` | Delete confirmation |
| `/debt` | Debt summary |
| `show invoice` | Invoice HTML or "Chưa có hóa đơn" |

- [ ] **Step 3: Verify Node.js is NOT double-processing**

```bash
cd /Users/duydinh0225/Documents/final_telegram
tail -20 /tmp/final_telegram.log | grep -i "soan\|giao\|task\|del"
```

Expected: No task command processing logs (Telethon handles them)

- [ ] **Step 4: Final commit**

```bash
# If any fixes were needed:
git commit -am "fix: integration fixes after full migration"
```

---

## Dependency Graph

```
Phase A (order_db.py extend)
    │
    ├──────────────┐
    │              │
Phase B         Phase C (can run in parallel with B)
(order_commands_v2)  (kiotviet.py + payment_db.py + order_commands_v3)
    │              │
    └──────┬───────┘
           │
      Phase D (integration)
```

- Phase B and C are **independent** — can be implemented by separate subagents in parallel
- Phase D runs after both B and C are complete
