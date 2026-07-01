from __future__ import annotations

import json
import logging
import os
import sqlite3
import time

from telethon import events
from telethon.tl.functions.messages import CreateForumTopicRequest
from telethon.tl.types import MessageService, UpdateNewChannelMessage, UpdateNewMessage

from firebase_sync import set_customer
from kiotviet import create_customer_kv

log = logging.getLogger("newkh")
GROUP_KHACHHANG_ID = int(os.getenv("GROUP_KHACHHANG_ID", 0))
from utils.paths import SHARED_DB_PATH
TRIGGER_TEXT = "newkh "


def _conn():
    conn = sqlite3.connect(SHARED_DB_PATH, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def _save(thread_id: int, data: dict):
    conn = _conn()
    try:
        conn.execute("INSERT INTO customers(firebase_key, json, updated_at, deleted_at) VALUES (?, ?, ?, NULL) ON CONFLICT(firebase_key) DO UPDATE SET json=excluded.json, updated_at=excluded.updated_at, deleted_at=NULL", (str(thread_id), json.dumps(data, ensure_ascii=False), int(time.time() * 1000)))
    finally:
        conn.close()


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())


def register_newkh_handler(client):
    if not GROUP_KHACHHANG_ID:
        log.warning("GROUP_KHACHHANG_ID not configured — newkh handler disabled")
        return

    @client.on(events.NewMessage(chats=GROUP_KHACHHANG_ID))
    async def on_newkh(event):
        msg = event.message
        if isinstance(msg, MessageService) or not (msg.text or "").startswith(TRIGGER_TEXT):
            return
        name = (msg.text or "")[len(TRIGGER_TEXT):].strip()
        if not name:
            await event.reply("❌ Vui lòng cung cấp tên khách hàng.\nVí dụ: `newkh Tên Khách Hàng Mới`", parse_mode="markdown")
            return
        processing_msg = None
        try:
            processing_msg = await event.reply("⏳ Đang xử lý tạo khách hàng mới...")
            kv = await client.loop.run_in_executor(None, lambda: create_customer_kv({"name": name}))
            if not kv or not kv.get("id"):
                raise RuntimeError("Không nhận được thông tin khách hàng hợp lệ từ KiotViet.")
            peer = await client.get_input_entity(GROUP_KHACHHANG_ID)
            result = await client(CreateForumTopicRequest(peer=peer, title=kv.get("name", name), random_id=int.from_bytes(os.urandom(8), "big") & 0x7FFFFFFFFFFFFFFF))
            thread_id = next((u.message.id for u in result.updates if isinstance(u, (UpdateNewChannelMessage, UpdateNewMessage))), None)
            if thread_id is None:
                raise RuntimeError("Không lấy được thread_id từ topic mới tạo.")
            data = {"name": kv.get("name", name), "contactNumber": kv.get("contactNumber", ""), "address": kv.get("address", ""), "thread_id": thread_id, "kh_id": kv["id"], "createdDate": _now_iso()}
            set_customer(thread_id, data)
            _save(thread_id, data)
            if processing_msg:
                await client.delete_messages(GROUP_KHACHHANG_ID, [processing_msg.id])
            await client.send_message(GROUP_KHACHHANG_ID, f"✅ Đã tạo khách hàng mới thành công!\n\n<b>Tên:</b> {data['name']}\n<b>ID KiotViet:</b> {data['kh_id']}\n<b>SĐT:</b> {data['contactNumber'] or 'Chưa có'}\n<b>Địa chỉ:</b> {data['address'] or 'Chưa có'}\n\n👉 Cuộc hội thoại đã được tạo cho khách hàng này.", reply_to=thread_id, parse_mode="html")
            log.info("Created customer '%s' kv_id=%s thread_id=%s", data["name"], data["kh_id"], thread_id)
        except Exception as e:
            log.exception("newkh error: %s", e)
            error_text = f"❌ Đã xảy ra lỗi khi tạo khách hàng mới: {e}"
            if processing_msg:
                try:
                    await client.edit_message(GROUP_KHACHHANG_ID, processing_msg.id, error_text)
                except Exception:
                    await event.reply(error_text)
            else:
                await event.reply(error_text)
