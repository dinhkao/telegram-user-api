from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
import time

from telethon import events
from telethon.tl.types import MessageService

from .thread_utils import extract_thread_id
log = logging.getLogger("what_data")
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))
from utils.paths import SHARED_DB_PATH
from utils.db import get_connection
TRIGGER_TEXT = "what data"


def _conn():
    return get_connection(SHARED_DB_PATH, readonly=True, busy_timeout=2000)


def _order_raw(conn, thread_id: int):
    row = conn.execute("SELECT json FROM orders WHERE thread_id = ?", (thread_id,)).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return {"_raw": str(row[0])}


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
def _build_html(data: dict, thread_id: int, elapsed_ms: float) -> str:
    def val(key, default="—"):
        v = data.get(key)
        return v if v not in (None, "") else default

    def money(key):
        try:
            return f"{int(data.get(key, 0) or 0):,}"
        except Exception:
            return str(data.get(key, 0))

    def ts(entry, step=""):
        if not isinstance(entry, dict):
            entry = {}
        status = "✅" if entry.get("done") else "🔘" if entry.get("skip") else "📦" if step == "soan_hang" and data.get("stock_confirmed") else "❌"
        note = f" ({entry.get('note')})" if entry.get("note") else ""
        return f"{status}{note}"

    items, total = [], 0
    for it in data.get("invoice") or data.get("invoice_items") or []:
        if isinstance(it, dict):
            sl, pr = int(it.get("sl", 0) or 0), int(it.get("price", 0) or 0)
            total += sl * pr
            items.append(f"<tr><td>{_esc(str(it.get('sp', '')))}</td><td>{sl}</td><td>{pr:,}</td><td>{sl * pr:,}</td></tr>")
    payments = "".join(f"<tr><td>{_esc(str(p.get('method', '')))}</td><td>{int(p.get('amount', 0) or 0):,}</td><td>{_esc(str(p.get('note', '')))}</td></tr>" for p in data.get("payments") or [] if isinstance(p, dict))
    return f"<!DOCTYPE html><html lang='vi'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>Đơn hàng #{thread_id}</title><style>body{{font-family:Segoe UI,Roboto,sans-serif;margin:20px;background:#f5f5f5}}.card{{background:#fff;border-radius:12px;padding:20px;margin-bottom:16px;box-shadow:0 2px 8px rgba(0,0,0,.06)}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:8px 6px;text-align:left;border-bottom:1px solid #eee}}.money{{font-family:monospace;text-align:right}}.total{{font-weight:600;color:#2e7d32}}</style></head><body><div class='card'><h1>Đơn hàng #{thread_id}</h1><div><b>Tên:</b> {_esc(str(val('text')))}</div><div><b>Khách:</b> {_esc(str(val('kh', val('customer_name'))))} (ID: {val('khach_hang_id', val('khID'))})</div><div><b>KV Invoice:</b> {val('kiotvietInvoiceCode', val('kiotvietInvoiceID', '—'))}</div></div><div class='card'><h2>🧾 Hóa đơn</h2>{'<table><tr><th>SP</th><th>SL</th><th>Giá</th><th>Tổng</th></tr>' + ''.join(items) + f'<tr><td colspan=3><b>Tổng hàng</b></td><td><b>{total:,}</b></td></tr></table>' if items else '<p><i>Chưa có sản phẩm</i></p>'}</div><div class='card'><h2>📊 Tổng kết</h2><table><tr><td>Tổng hàng</td><td class='money'>{total:,}</td></tr><tr><td>Giảm</td><td class='money'>-{money('discount')}</td></tr><tr><td>Ship</td><td class='money'>+{money('pvc')}</td></tr><tr><td>VAT</td><td class='money'>+{money('vat')}</td></tr><tr><td><b>Tổng đơn</b></td><td class='money total'>{total + int(data.get('pvc', 0) or 0) + int(data.get('vat', 0) or 0) - int(data.get('discount', 0) or 0):,}</td></tr><tr><td>Nợ trước</td><td class='money'>{money('khDebt')}</td></tr><tr><td><b>Tổng thanh toán</b></td><td class='money total'>{total + int(data.get('pvc', 0) or 0) + int(data.get('vat', 0) or 0) - int(data.get('discount', 0) or 0) + int(data.get('khDebt', 0) or 0):,}</td></tr></table></div><div class='card'><h2>💸 Thanh toán</h2>{'<table><tr><th>Phương thức</th><th>Số tiền</th><th>Ghi chú</th></tr>' + payments + '</table>' if payments else '<p><i>Chưa có thanh toán</i></p>'}</div><div class='card'><h2>📋 Trạng thái</h2><table><tr><td>Bán HĐ</td><td>{ts(data.get('task_status', {}).get('ban_hd'), 'ban_hd')}</td></tr><tr><td>Soạn hàng</td><td>{ts(data.get('task_status', {}).get('soan_hang'), 'soan_hang')}</td></tr><tr><td>Giao hàng</td><td>{ts(data.get('task_status', {}).get('giao_hang'), 'giao_hang')}</td></tr><tr><td>Nộp tiền</td><td>{ts(data.get('task_status', {}).get('nop_tien'), 'nop_tien')}</td></tr><tr><td>Nhận tiền</td><td>{ts(data.get('task_status', {}).get('nhan_tien'), 'nhan_tien')}</td></tr></table></div><div style='font-size:11px;color:#aaa;text-align:center;margin-top:20px'>Generated in {elapsed_ms:.1f}ms • what_data</div></body></html>"


def register_what_data_handler(client):
    db_conn = _conn()
    log.info("listening on chat %d for '%s'. DB: %s", ORDER_GROUP_ID, TRIGGER_TEXT, SHARED_DB_PATH)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_msg(event):
        msg = event.message
        if isinstance(msg, MessageService) or (msg.text or "").strip().lower() != TRIGGER_TEXT:
            return
        thread_id = extract_thread_id(msg)
        if not thread_id:
            await client.send_message(msg.chat_id, "❌ Could not determine thread_id from this message.", reply_to=msg.id)
            return
        t0 = time.monotonic()
        try:
            data = _order_raw(db_conn, thread_id)
        except Exception as e:
            await client.send_message(msg.chat_id, f"❌ DB error: {e}", reply_to=msg.id)
            return
        elapsed = (time.monotonic() - t0) * 1000
        if data is None:
            await client.send_message(msg.chat_id, f"❌ Order not found (thread {thread_id}, {elapsed:.1f}ms)", reply_to=msg.id)
            return
        file_path = os.path.join(tempfile.gettempdir(), f"order_{thread_id}_{int(time.time())}.html")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(_build_html(data, thread_id, elapsed))
        try:
            await client.send_file(msg.chat_id, file_path, caption=f"📄 Order #{thread_id} • {elapsed:.1f}ms", reply_to=msg.id, force_document=True)
        finally:
            try:
                os.remove(file_path)
            except OSError:
                pass
