"""Tạo khách hàng mới từ web app — POST /api/customers/new.
Giống lệnh Telegram `newkh` (command_handlers/newkh_handler): tạo khách trên KiotViet
→ mở forum topic trong GROUP_KHACHHANG_ID (user client) → lưu vào bảng customers
(key = thread_id) + Firebase + realtime. Đăng ký ở server_app/app_factory.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from aiohttp import web

from order_db import _get_connection

log = logging.getLogger("server")

GROUP_KHACHHANG_ID = int(os.getenv("GROUP_KHACHHANG_ID", "0") or "0")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())


def _save(thread_id: int, data: dict) -> None:
    conn = _get_connection()
    try:
        conn.execute(
            "INSERT INTO customers(firebase_key, json, updated_at, deleted_at) VALUES (?, ?, ?, NULL) "
            "ON CONFLICT(firebase_key) DO UPDATE SET json=excluded.json, updated_at=excluded.updated_at, deleted_at=NULL",
            (str(thread_id), json.dumps(data, ensure_ascii=False), int(time.time() * 1000)),
        )
        try:
            conn.commit()
        except Exception:  # noqa: BLE001 — autocommit mode
            pass
    finally:
        conn.close()


async def customer_create_handler(request: web.Request):
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return web.json_response({"ok": False, "error": "body phải là JSON"}, status=400)

    name = str(body.get("name") or "").strip()
    if not name:
        return web.json_response({"ok": False, "error": "Thiếu tên khách hàng"}, status=400)
    phone = str(body.get("contactNumber") or body.get("phone") or "").strip()
    address = str(body.get("address") or "").strip()

    # 1. Tạo khách trên KiotViet (blocking → thread)
    from kiotviet import create_customer_kv
    try:
        kv = await asyncio.to_thread(create_customer_kv, {"name": name, "contactNumber": phone, "address": address})
    except Exception as e:  # noqa: BLE001
        log.warning("Tạo khách KiotViet lỗi: %s", e)
        return web.json_response({"ok": False, "error": f"Lỗi tạo khách KiotViet: {e}"}, status=502)
    if not kv or not kv.get("id"):
        return web.json_response({"ok": False, "error": "KiotViet không trả về khách hợp lệ"}, status=502)

    # 2. Mở forum topic khách (cần user client + group đã cấu hình)
    from server_app import state
    client = state._client
    if client is None or not GROUP_KHACHHANG_ID:
        return web.json_response({"ok": False, "error": "Chưa cấu hình nhóm khách / client Telegram"}, status=503)
    try:
        from telethon.tl.functions.messages import CreateForumTopicRequest
        from telethon.tl.types import UpdateNewChannelMessage, UpdateNewMessage
        peer = await client.get_input_entity(GROUP_KHACHHANG_ID)
        result = await client(CreateForumTopicRequest(
            peer=peer, title=kv.get("name", name),
            random_id=int.from_bytes(os.urandom(8), "big") & 0x7FFFFFFFFFFFFFFF))
        thread_id = next((u.message.id for u in result.updates
                          if isinstance(u, (UpdateNewChannelMessage, UpdateNewMessage))), None)
    except Exception as e:  # noqa: BLE001
        log.warning("Mở topic khách lỗi: %s", e)
        return web.json_response({"ok": False, "error": f"Lỗi mở topic khách: {e}"}, status=502)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "Không lấy được thread_id topic khách"}, status=502)

    # 3. Lưu customers + Firebase
    data = {
        "name": kv.get("name", name),
        "contactNumber": kv.get("contactNumber", phone),
        "address": kv.get("address", address),
        "thread_id": thread_id,
        "kh_id": kv["id"],
        "createdDate": _now_iso(),
    }
    await asyncio.to_thread(_save, thread_id, data)
    try:
        from firebase_sync import set_customer
        set_customer(thread_id, data)
    except Exception as e:  # noqa: BLE001
        log.warning("Firebase set_customer lỗi (bỏ qua): %s", e)

    # 4. Realtime → trang Khách refetch
    from server_app.realtime import emit_customer_changed
    emit_customer_changed(str(thread_id))

    log.info("Web tạo khách '%s' kv_id=%s thread=%s", data["name"], data["kh_id"], thread_id)
    return web.json_response({"ok": True, "customer": {
        "key": str(thread_id), "name": data["name"], "kh_id": data["kh_id"],
        "contactNumber": data["contactNumber"], "address": data["address"], "thread_id": thread_id,
    }})
