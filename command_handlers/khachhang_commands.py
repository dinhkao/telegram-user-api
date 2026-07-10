from __future__ import annotations

import logging
import os
import re

from telethon import events
from telethon.tl.types import MessageService

from order_db import _get_connection, get_customer_by_key, get_customer_price_list, update_customer

from .thread_utils import extract_thread_id

log = logging.getLogger("khachhang_commands")
GROUP_KHACHHANG_ID = int(os.getenv("GROUP_KHACHHANG_ID", 0))
VALID_PRODUCT_CODES = {"K10LV87", "K10LV85", "K10LT", "K10TV80", "K10NV60", "K10LV87-M", "K10LV87-TD", "K2L", "K2L-TD", "K1L", "K2LBN", "K2NT", "K2NV120", "K2NV128", "KD2M", "KD2M-TD", "KDBN2M", "KDBN1L", "KDDT", "KDDT180", "KDDT200", "KDDT470", "KDDT480", "KDDT500", "DMX", "DM180", "DM450", "DM45", "DM40", "DM50", "DM50N", "DM500B", "DM300", "DM250", "DM30N", "DM126MY", "DM126LCMY", "DM205LCMY", "KDXDB", "KGL", "KMT", "KMD", "KHDX", "KMT470", "KMD470", "KTC350", "KTC450", "DRV", "DRV450", "KDG", "KDXL1", "KDXL2", "KDXDB-G", "KDXL1-G", "KDV180DB", "KDV200DB", "KDV230DB", "KDV250DB", "KDV380DB", "KDV400DB", "KDV470DB", "KDV480DB", "KDV500DB", "KDV500DB-T", "KDV180L1", "KDV200L1", "KDV230L1", "KDV250L1", "KDV380L1", "KDV400L1", "KDV470L1", "KDV480L1", "KDV500L1", "KDG380", "KDG470", "KHD230", "KHD250", "KHD470", "KHD500", "KGL250", "KGL500-T", "KGLHG180", "KMT380", "KVGHG200", "KVHHG200", "PLT-DB", "PLTL", "HQT", "KTC"}


def register_khachhang_commands(client):
    if not GROUP_KHACHHANG_ID:
        log.warning("GROUP_KHACHHANG_ID not configured — khachhang commands disabled")
        return
    db_conn = _get_connection()

    @client.on(events.NewMessage(chats=GROUP_KHACHHANG_ID))
    async def on_kh(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return
        parts = (msg.text or "").strip().split()
        if len(parts) == 1:
            code = parts[0].upper()
            if code in VALID_PRODUCT_CODES and code not in {"?", "GETJSON", "SP", "AP", "DP", "NEWKH", "NEW", "EDITKH", "GET", "ADD", "CLEAR", "LINK", "UPDATE", "SHOW", "DELETE"}:
                thread_id = extract_thread_id(msg)
                if not thread_id:
                    await client.send_message(msg.chat_id, "❌ Không thể xác định khách hàng cho cuộc trò chuyện này.", reply_to=msg.id)
                    return
                customer = get_customer_by_key(db_conn, str(thread_id))
                if not customer:
                    await client.send_message(msg.chat_id, "❌ Không tìm thấy thông tin khách hàng.", reply_to=msg.id)
                    return
                price = get_customer_price_list(db_conn, str(thread_id)).get(code)
                await client.send_message(msg.chat_id, f"Giá: <b>{int(price):,}</b>" if price else f"Không tìm thấy giá cho sản phẩm <b>{code}</b>.", reply_to=msg.id, parse_mode="html")
            return
        if len(parts) == 2:
            code, price_str = parts[0].upper(), parts[1]
            if code in VALID_PRODUCT_CODES and re.match(r"^\d+$", price_str):
                thread_id = extract_thread_id(msg)
                if not thread_id:
                    await client.send_message(msg.chat_id, "❌ Không thể xác định khách hàng cho cuộc trò chuyện này.", reply_to=msg.id)
                    return
                customer = get_customer_by_key(db_conn, str(thread_id))
                if not customer:
                    await client.send_message(msg.chat_id, "❌ Không tìm thấy thông tin khách hàng.", reply_to=msg.id)
                    return
                from price_list_store.keys import to_pid_key
                personal = customer.get("personal_price_list") or {}
                personal[to_pid_key(db_conn, code)] = int(price_str)
                customer["personal_price_list"] = personal
                ok, _ = update_customer(db_conn, str(thread_id), customer)
                if ok:   # ghi Lịch sử thao tác khách (best-effort, không chặn lệnh)
                    try:
                        from audit_log import async_log_event
                        await async_log_event("customer.edited", scope="customer", thread_id=int(thread_id),
                                              actor_type="telegram", actor_id=str(getattr(msg, "sender_id", "") or "?"),
                                              source="telegram:price", payload={"detail": f"giá riêng {code} = {int(price_str):,}"})
                    except Exception:  # noqa: BLE001
                        pass
                await client.send_message(msg.chat_id, f"Đã cập nhật giá riêng cho sản phẩm <b>{code}</b> thành <b>{int(price_str):,}</b>." if ok else "❌ Lỗi lưu giá riêng.", reply_to=msg.id, parse_mode="html")
