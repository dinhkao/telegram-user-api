"""gdt_handler.py — Giấy dán thùng commands for group-chat order topics.

gdt  <ten>; <sdt>; <so_thung>; <note>   → save giay_dan_thung to order JSON
ingdt                                     → generate HTML label and send as document
"""
from __future__ import annotations
import logging
import os
import tempfile

from telethon import events
from telethon.tl.types import MessageService

from order_db import _get_connection, get_order_by_thread_id, _save_order

log = logging.getLogger("gdt_handler")
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


def register_gdt_handler(client):
    db_conn = _get_connection()

    # ── Command: gdt <ten>; <sdt>; <so_thung>; <note> ──────────────────
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
            if payload.startswith(":") or payload.startswith("-") or payload.startswith("="):
                payload = payload[1:].strip()

            parts = [p.strip() for p in payload.split(";")]
            if len(parts) < 4:
                await client.send_message(
                    msg.chat_id,
                    "❌ Định dạng: gdt Tên; SĐT; Số thùng; Ghi chú",
                    reply_to=msg.id,
                )
                return

            ten_gdt, sdt_gdt, so_thung, note_gdt = parts
            gdt_data = {
                "ten_gdt": ten_gdt,
                "sdt_gdt": sdt_gdt,
                "so_thung": so_thung,
                "note_gdt": note_gdt,
            }

            thread_id = _extract_thread_id(msg)
            if not thread_id:
                await client.send_message(
                    msg.chat_id,
                    "❌ Không xác định được topic đơn hàng",
                    reply_to=msg.id,
                )
                return

            order = get_order_by_thread_id(db_conn, thread_id)
            if not order:
                await client.send_message(
                    msg.chat_id,
                    "❌ Không tìm thấy đơn hàng",
                    reply_to=msg.id,
                )
                return

            order["giay_dan_thung"] = gdt_data
            if _save_order(db_conn, thread_id, order):
                await client.send_message(
                    msg.chat_id,
                    "✅ Cập nhật giấy dán thùng thành công",
                    reply_to=msg.id,
                )
            else:
                await client.send_message(
                    msg.chat_id,
                    "❌ Lỗi lưu giấy dán thùng",
                    reply_to=msg.id,
                )
        except Exception as e:
            log.error("gdt command error: %s", e, exc_info=True)
            await client.send_message(
                msg.chat_id,
                "❌ Lỗi khi cập nhật giấy dán thùng",
                reply_to=msg.id,
            )

    # ── Command: ingdt (generate HTML label and upload) ──────────────
    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def on_ingdt(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return
        if (msg.text or "").strip().lower() != "ingdt":
            return

        try:
            thread_id = _extract_thread_id(msg)
            if not thread_id:
                await client.send_message(
                    msg.chat_id,
                    "❌ Không xác định được topic đơn hàng",
                    reply_to=msg.id,
                )
                return

            order = get_order_by_thread_id(db_conn, thread_id)
            if not order:
                await client.send_message(
                    msg.chat_id,
                    "❌ Không tìm thấy đơn hàng",
                    reply_to=msg.id,
                )
                return

            gdt = order.get("giay_dan_thung")
            if not gdt:
                await client.send_message(
                    msg.chat_id,
                    "ℹ️ Chưa có thông tin giấy dán thùng",
                    reply_to=msg.id,
                )
                return

            template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vertical Text Layout</title>
    <style>
        body { display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background-color: #f0f0f0; }
        .container { width: 80mm; height: 297mm; display: flex; flex-direction: column; justify-content: space-around; align-items: center; writing-mode: vertical-rl; font-family: Arial, sans-serif; font-weight: bold; font-size: 40px; line-height: 1px; overflow: hidden; }
        input { writing-mode: horizontal-tb; width: 10px; font-size: 40px; font-family: Arial, sans-serif; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <p style="margin-bottom:0;margin:0; padding-top:0;">Người gửi: Kẹo Lê Trang 0941 586 542</p>
        <p style="margin:0; padding-top:0;">Người nhận:nguoinhan sdt &emsp;&emsp;&emsp;.</p>
        <p style="margin:0; padding-top:0;">sothung (thùng)</p>
        <p style="margin:0; padding-top:0;">note</p>
    </div>
</body>
</html>"""

            def _replace_all(s: str, old: str, new: str) -> str:
                return new.join(s.split(old))

            content = template
            content = _replace_all(content, "nguoinhan", str(gdt.get("ten_gdt", "")))
            content = _replace_all(content, "sdt", str(gdt.get("sdt_gdt", "")))
            content = _replace_all(content, "sothung", str(gdt.get("so_thung", "")))
            content = _replace_all(content, "note", str(gdt.get("note_gdt", "")))

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".html", delete=False, encoding="utf-8"
            ) as f:
                f.write(content)
                file_path = f.name

            await client.send_file(
                msg.chat_id,
                file_path,
                reply_to=msg.id,
                force_document=True,
            )

            try:
                os.remove(file_path)
            except OSError:
                pass

        except Exception as e:
            log.error("ingdt command error: %s", e, exc_info=True)
            await client.send_message(
                msg.chat_id,
                "❌ Lỗi khi in giấy dán thùng",
                reply_to=msg.id,
            )
