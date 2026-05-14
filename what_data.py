"""what_data.py — Fast HTML-file order viewer for group topic messages.

Listens for "what data" in the order group chat. Extracts the topic/thread ID,
queries the shared final_telegram SQLite database directly, and replies with
a small HTML file that can be opened to view the order in a clean table layout.

Fits into server.py's register_handlers(client) call.
"""
from __future__ import annotations
import json
import logging
import os
import sqlite3
import tempfile
import time
from telethon import events
from telethon.tl.types import MessageService

log = logging.getLogger("what_data")

# The main order group where each order is a forum topic
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))

# Path to the shared SQLite database owned by final_telegram
SHARED_DB_PATH = os.path.expanduser(
    os.getenv("SHARED_DB_PATH", "~/Documents/final_telegram/data/app.db")
)

# Trigger text (case-insensitive comparison)
TRIGGER_TEXT = "what data"

# Telegram user ID → display name (same as bot-don-hang/config.py)
USER_NAMES = {
    "1809874974": "Duy",
    "6970077624": "Tùng",
    "6964088058": "Trinh",
    "7569624990": "Tuấn",
    "6730500620": "Trang",
    "7158345531": "Trí",
}


def _name_of_user_id(uid) -> str:
    if uid is None or uid == "":
        return ""
    return USER_NAMES.get(str(uid), str(uid))


def _get_order_raw(conn, thread_id: int) -> dict | None:
    """Query the orders table by thread_id. Returns the full JSON or None."""
    row = conn.execute(
        "SELECT json FROM orders WHERE thread_id = ? AND deleted_at IS NULL",
        (thread_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return {"_raw": str(row[0])}


def _build_order_html(data: dict, thread_id: int, elapsed_ms: float) -> str:
    """Build a compact, readable HTML page from the order JSON."""

    def val(key, default="—"):
        v = data.get(key)
        return v if v is not None and v != "" else default

    def money(key, default=0):
        v = data.get(key, default)
        try:
            return f"{int(v):,}"
        except Exception:
            return str(v)

    def fmt_ts(entry):
        if not entry or not isinstance(entry, dict):
            return "—"
        by_raw = entry.get("by", "")
        by_name = _name_of_user_id(by_raw)
        done = entry.get("done", False)
        skip = entry.get("skip", False)
        note = entry.get("note", "")
        status = "✅" if done else ("🔘" if skip else "❌")
        note_str = f" ({note})" if note else ""
        return f"{status}{note_str} — {by_name}" if by_name else f"{status}{note_str}"

    text = _escape_html(val("text"))
    kh = _escape_html(val("kh", val("customer_name")))
    kh_id = val("khach_hang_id", val("khID"))
    kv_id = val("kiotvietInvoiceID", val("kiotviet_invoice_id"))
    kv_code = val("kiotvietInvoiceCode", "")

    invoice_items = data.get("invoice") or data.get("invoice_items") or []
    rows = []
    total = 0
    for it in invoice_items:
        if not isinstance(it, dict):
            continue
        sp = _escape_html(str(it.get("sp", "")))
        sl = int(it.get("sl", 0) or 0)
        pr = int(it.get("price", 0) or 0)
        line_total = sl * pr
        total += line_total
        rows.append(
            f"<tr><td>{sp}</td><td>{sl}</td><td>{pr:,}</td><td>{line_total:,}</td></tr>"
        )

    invoice_table = (
        "<table><tr><th>SP</th><th>SL</th><th>Giá</th><th>Tổng</th></tr>"
        + "".join(rows)
        + f"<tr><td colspan=3><b>Tổng hàng</b></td><td><b>{total:,}</b></td></tr></table>"
        if rows
        else "<p><i>Chưa có sản phẩm</i></p>"
    )

    ts = data.get("task_status") or {}

    discount = money("discount")
    pvc = money("pvc")
    vat = money("vat")
    kh_debt = money("khDebt")
    order_total = total + int(data.get("pvc", 0) or 0) + int(data.get("vat", 0) or 0) - int(data.get("discount", 0) or 0)
    final_total = order_total + int(data.get("khDebt", 0) or 0)

    payments = data.get("payments") or []
    pay_rows = []
    for p in payments:
        if not isinstance(p, dict):
            continue
        amt = int(p.get("amount", 0) or 0)
        method = _escape_html(str(p.get("method", "")))
        note = _escape_html(str(p.get("note", "")))
        pay_rows.append(f"<tr><td>{method}</td><td>{amt:,}</td><td>{note}</td></tr>")
    pay_table = (
        "<table><tr><th>Phương thức</th><th>Số tiền</th><th>Ghi chú</th></tr>"
        + "".join(pay_rows)
        + "</table>"
        if pay_rows
        else "<p><i>Chưa có thanh toán</i></p>"
    )

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Đơn hàng #{thread_id}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 20px; background: #f5f5f5; }}
  .card {{ background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
  h1 {{ font-size: 18px; margin: 0 0 8px; color: #1a1a1a; }}
  h2 {{ font-size: 14px; margin: 0 0 12px; color: #555; text-transform: uppercase; letter-spacing: 0.5px; }}
  .meta {{ font-size: 13px; color: #666; margin-bottom: 4px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 8px 6px; text-align: left; border-bottom: 1px solid #eee; }}
  th {{ color: #888; font-weight: 500; }}
  tr:last-child td {{ border-bottom: none; }}
  .money {{ font-family: "SF Mono", Monaco, monospace; text-align: right; }}
  .total {{ font-weight: 600; color: #2e7d32; }}
  .status {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; background: #e3f2fd; color: #1565c0; }}
  .footer {{ font-size: 11px; color: #aaa; text-align: center; margin-top: 20px; }}
</style>
</head>
<body>
<div class="card">
  <h1>Đơn hàng #{thread_id}</h1>
  <div class="meta"><b>Tên:</b> {text}</div>
  <div class="meta"><b>Khách:</b> {kh} (ID: {kh_id})</div>
  <div class="meta"><b>KV Invoice:</b> {kv_code or kv_id or "—"}</div>
</div>

<div class="card">
  <h2>🧾 Hóa đơn</h2>
  {invoice_table}
</div>

<div class="card">
  <h2>📊 Tổng kết</h2>
  <table>
    <tr><td>Tổng hàng</td><td class="money">{total:,}</td></tr>
    <tr><td>Giảm</td><td class="money">-{discount}</td></tr>
    <tr><td>Ship</td><td class="money">+{pvc}</td></tr>
    <tr><td>VAT</td><td class="money">+{vat}</td></tr>
    <tr><td><b>Tổng đơn</b></td><td class="money total">{order_total:,}</td></tr>
    <tr><td>Nợ trước</td><td class="money">{kh_debt}</td></tr>
    <tr><td><b>Tổng thanh toán</b></td><td class="money total">{final_total:,}</td></tr>
  </table>
</div>

<div class="card">
  <h2>💸 Thanh toán</h2>
  {pay_table}
</div>

<div class="card">
  <h2>📋 Trạng thái</h2>
  <table>
    <tr><td>Bán HĐ</td><td>{fmt_ts(ts.get("ban_hd"))}</td></tr>
    <tr><td>Soạn hàng</td><td>{fmt_ts(ts.get("soan_hang"))}</td></tr>
    <tr><td>Giao hàng</td><td>{fmt_ts(ts.get("giao_hang"))}</td></tr>
    <tr><td>Nộp tiền</td><td>{fmt_ts(ts.get("nop_tien"))}</td></tr>
    <tr><td>Nhận tiền</td><td>{fmt_ts(ts.get("nhan_tien"))}</td></tr>
  </table>
</div>

<div class="footer">Generated in {elapsed_ms:.1f}ms • what_data</div>
</body>
</html>"""
    return html


def _escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _get_connection():
    """Open a new read-only WAL connection (fast, no schema changes)."""
    conn = sqlite3.connect(
        f"file:{SHARED_DB_PATH}?mode=ro",
        uri=True,
        check_same_thread=False,
        isolation_level=None,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=2000;")
    return conn


def register_what_data_handler(client):
    """Attach the 'what data' event handler. Called from server.py."""

    db_conn = _get_connection()
    log.info("listening on chat %d for '%s'. DB: %s", ORDER_GROUP_ID, TRIGGER_TEXT, SHARED_DB_PATH)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_order_group_message(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return

        text = (msg.text or "").strip()
        if text.lower() != TRIGGER_TEXT:
            return

        log.debug("what_data triggered by sender=%s", getattr(msg, "sender_id", "?"))

        # Extract topic/thread ID (forum topics use reply_to.reply_to_top_id)
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

        if not thread_id:
            log.warning("what_data: could not determine thread_id for msg %d", msg.id)
            await client.send_message(
                msg.chat_id,
                "❌ Could not determine thread_id from this message.",
                reply_to=msg.id,
            )
            return

        log.debug("what_data: extracted thread_id=%d for msg %d", thread_id, msg.id)

        t0 = time.monotonic()
        try:
            data = _get_order_raw(db_conn, thread_id)
        except Exception as e:
            log.error("what_data DB error: thread=%d error=%s", thread_id, e)
            await client.send_message(
                msg.chat_id,
                f"❌ DB error: {e}",
                reply_to=msg.id,
            )
            return

        elapsed = (time.monotonic() - t0) * 1000

        if data is None:
            await client.send_message(
                msg.chat_id,
                f"❌ Order not found (thread {thread_id}, {elapsed:.1f}ms)",
                reply_to=msg.id,
            )
            return

        # Build HTML file
        html = _build_order_html(data, thread_id, elapsed)
        file_path = os.path.join(tempfile.gettempdir(), f"order_{thread_id}_{int(time.time())}.html")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html)

        try:
            await client.send_file(
                msg.chat_id,
                file_path,
                caption=f"📄 Order #{thread_id} • {elapsed:.1f}ms",
                reply_to=msg.id,
                force_document=True,
            )
            who = getattr(msg, "sender_id", "?")
            log.info("thread=%d html=%dB %.1fms asked by %s", thread_id, len(html), elapsed, who)
        except Exception as e:
            log.error("what_data send file error: %s", e)
            await client.send_message(
                msg.chat_id,
                f"❌ Failed to send HTML file: {e}",
                reply_to=msg.id,
            )
        finally:
            try:
                os.unlink(file_path)
            except Exception:
                pass
