"""newkh_handler.py — 'newkh <name>' command in KhachHang group.

Mirrors Node.js groupKhachHang.js newkh handler:
1. Create KiotViet customer
2. Create Telegram forum topic
3. Save to Firebase + SQLite
4. Send confirmation in new topic
"""
from __future__ import annotations
import json
import logging
import os
import sqlite3
import time

from telethon import events
from telethon.tl.functions.channels import CreateForumTopicRequest
from telethon.tl.types import (
    MessageService,
    UpdateNewChannelMessage,
    UpdateNewMessage,
)

from kiotviet import create_customer_kv
from firebase_sync import set_customer

log = logging.getLogger("newkh")

GROUP_KHACHHANG_ID = int(os.getenv("GROUP_KHACHHANG_ID", 0))
SHARED_DB_PATH = os.path.expanduser(
    os.getenv("SHARED_DB_PATH", "~/Documents/final_telegram/data/app.db")
)
TRIGGER_TEXT = "newkh "


def _get_write_conn():
    conn = sqlite3.connect(SHARED_DB_PATH, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def _save_customer_to_sqlite(thread_id: int, data: dict):
    conn = _get_write_conn()
    try:
        conn.execute(
            """INSERT INTO customers(firebase_key, json, updated_at, deleted_at)
               VALUES (?, ?, ?, NULL)
               ON CONFLICT(firebase_key) DO UPDATE SET
                   json = excluded.json,
                   updated_at = excluded.updated_at,
                   deleted_at = NULL""",
            (str(thread_id), json.dumps(data, ensure_ascii=False), int(time.time() * 1000)),
        )
    finally:
        conn.close()


def register_newkh_handler(client):
    if not GROUP_KHACHHANG_ID:
        log.warning("GROUP_KHACHHANG_ID not configured — newkh handler disabled")
        return

    log.info("newkh handler listening on chat %d", GROUP_KHACHHANG_ID)

    @client.on(events.NewMessage(chats=GROUP_KHACHHANG_ID))
    async def on_newkh(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return

        text = msg.text or ""
        if not text.startswith(TRIGGER_TEXT):
            return

        customer_name = text[len(TRIGGER_TEXT):].strip()
        if not customer_name:
            await event.reply(
                "❌ Vui lòng cung cấp tên khách hàng.\n"
                "Ví dụ: `newkh Tên Khách Hàng Mới`",
                parse_mode="markdown",
            )
            return

        processing_msg = None
        try:
            processing_msg = await event.reply("⏳ Đang xử lý tạo khách hàng mới...")

            # 1. Create KiotViet customer
            kv_customer = await client.loop.run_in_executor(
                None,
                lambda: create_customer_kv({"name": customer_name}),
            )

            if not kv_customer or not kv_customer.get("id"):
                raise RuntimeError("Không nhận được thông tin khách hàng hợp lệ từ KiotViet.")

            kv_id = kv_customer["id"]
            kv_name = kv_customer.get("name", customer_name)
            kv_phone = kv_customer.get("contactNumber", "")
            kv_address = kv_customer.get("address", "")

            # 2. Create Telegram forum topic
            peer = await client.get_input_entity(GROUP_KHACHHANG_ID)
            result = await client(
                CreateForumTopicRequest(
                    channel=peer,
                    title=kv_name,
                    random_id=int.from_bytes(os.urandom(8), "big"),
                )
            )

            # Extract thread_id from returned updates
            thread_id = None
            for update in result.updates:
                if isinstance(update, (UpdateNewChannelMessage, UpdateNewMessage)):
                    thread_id = update.message.id
                    break

            if thread_id is None:
                log.error("CreateForumTopic returned no message id: %s", result)
                raise RuntimeError("Không lấy được thread_id từ topic mới tạo.")

            # 3. Build data
            firebase_data = {
                "name": kv_name,
                "contactNumber": kv_phone,
                "address": kv_address,
                "thread_id": thread_id,
                "kh_id": kv_id,
                "createdDate": _now_iso(),
            }

            # 4. Save to Firebase
            set_customer(thread_id, firebase_data)

            # 5. Save to SQLite (immediate availability)
            _save_customer_to_sqlite(thread_id, firebase_data)

            # 6. Delete processing message
            if processing_msg:
                await client.delete_messages(GROUP_KHACHHANG_ID, [processing_msg.id])

            # 7. Send confirmation in new topic
            confirmation = (
                f"✅ Đã tạo khách hàng mới thành công!\n\n"
                f"<b>Tên:</b> {firebase_data['name']}\n"
                f"<b>ID KiotViet:</b> {firebase_data['kh_id']}\n"
                f"<b>SĐT:</b> {firebase_data['contactNumber'] or 'Chưa có'}\n"
                f"<b>Địa chỉ:</b> {firebase_data['address'] or 'Chưa có'}\n"
                f"\n👉 Cuộc hội thoại đã được tạo cho khách hàng này."
            )
            await client.send_message(
                GROUP_KHACHHANG_ID,
                confirmation,
                reply_to=thread_id,
                parse_mode="html",
            )

            log.info(
                "Created customer '%s' kv_id=%s thread_id=%s",
                kv_name, kv_id, thread_id,
            )

        except Exception as e:
            log.exception("newkh error: %s", e)
            error_text = f"❌ Đã xảy ra lỗi khi tạo khách hàng mới: {e}"
            if processing_msg:
                try:
                    await client.edit_message(
                        GROUP_KHACHHANG_ID, processing_msg.id, error_text
                    )
                except Exception:
                    await event.reply(error_text)
            else:
                await event.reply(error_text)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
