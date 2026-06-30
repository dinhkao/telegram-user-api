from __future__ import annotations

import logging
import os
import re
import tempfile

from telethon import events
from telethon.tl.types import MessageService

from order_db import _get_connection, _save_order, get_order_by_thread_id

from .thread_utils import extract_thread_id

log = logging.getLogger("gdt_handler")
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))


def register_gdt_handler(client):
    db_conn = _get_connection()

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_gdt(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return
        text = (msg.text or "").strip()
        if not text.lower().startswith("gdt"):
            return
        try:
            payload = text[3:].strip()
            if payload[:1] in ":-=":
                payload = payload[1:].strip()
            parts = [p.strip() for p in payload.split(";")]
            if len(parts) < 4:
                await client.send_message(msg.chat_id, "❌ Định dạng: gdt Tên; SĐT; Số thùng; Ghi chú", reply_to=msg.id)
                return
            thread_id = extract_thread_id(msg)
            if not thread_id:
                await client.send_message(msg.chat_id, "❌ Không xác định được topic đơn hàng", reply_to=msg.id)
                return
            order = get_order_by_thread_id(db_conn, thread_id)
            if not order:
                await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
                return
            order["giay_dan_thung"] = {"ten_gdt": parts[0], "sdt_gdt": parts[1], "so_thung": parts[2], "note_gdt": parts[3]}
            await client.send_message(msg.chat_id, "✅ Cập nhật giấy dán thùng thành công" if _save_order(db_conn, thread_id, order) else "❌ Lỗi lưu giấy dán thùng", reply_to=msg.id)
        except Exception as e:
            log.error("gdt command error: %s", e, exc_info=True)
            await client.send_message(msg.chat_id, "❌ Lỗi khi cập nhật giấy dán thùng", reply_to=msg.id)

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_ingdt(event):
        msg = event.message
        if isinstance(msg, MessageService) or (msg.text or "").strip().lower() != "ingdt":
            return
        thread_id = extract_thread_id(msg)
        if not thread_id:
            await client.send_message(msg.chat_id, "❌ Không xác định được topic đơn hàng", reply_to=msg.id)
            return
        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            await client.send_message(msg.chat_id, "❌ Không tìm thấy đơn hàng", reply_to=msg.id)
            return
        gdt = order.get("giay_dan_thung")
        if not gdt:
            await client.send_message(msg.chat_id, "ℹ️ Chưa có thông tin giấy dán thùng", reply_to=msg.id)
            return
        customer_name = (order.get("customer_name") or order.get("kh") or "khong_ten").strip()
        safe_name = re.sub(r"[^a-zA-Z0-9\u0080-\uffff_\- ]", "", customer_name.replace(" ", "_").replace("/", "_").replace("\\", "_"))[:50] or "gdt"
        file_path = os.path.join(tempfile.gettempdir(), f"gdt_{safe_name}.html")
        content = f"<!DOCTYPE html><html><body style='margin:0'><div style='writing-mode:vertical-rl;font:700 40px Arial;height:297mm;width:80mm;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:30px;text-align:center'><p style='margin:0'>Người gửi: Kẹo Lê Trang 0941 586 542</p><p style='margin:0'>Người nhận:{gdt.get('ten_gdt','')} {gdt.get('sdt_gdt','')}</p><p style='margin:0'>{gdt.get('so_thung','')} (thùng)</p><p style='margin:0'>{gdt.get('note_gdt','')}</p></div></body></html>"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        try:
            await client.send_file(msg.chat_id, file_path, reply_to=msg.id, force_document=True)
        finally:
            try:
                os.remove(file_path)
            except OSError:
                pass
