"""khachhang_commands.py — Product price lookup & personal price setting in KhachHang group.

Commands:
- <product_code>         → lookup price for this customer
- <product_code> <price> → set personal price override
"""
from __future__ import annotations
import json
import logging
import os
import re

from telethon import events
from telethon.tl.types import MessageService

from order_db import _get_connection, get_customer_price_list, get_customer_by_key, update_customer

log = logging.getLogger("khachhang_commands")

GROUP_KHACHHANG_ID = int(os.getenv("GROUP_KHACHHANG_ID", 0))

# ── Valid product codes (mirrors final_telegram/config/products.js) ──
VALID_PRODUCT_CODES = {
    "K10LV87", "K10LV85", "K10LT", "K10TV80", "K10NV60", "K10LV87-M", "K10LV87-TD",
    "K2L", "K2L-TD", "K1L", "K2LBN", "K2NT", "K2NV120", "K2NV128",
    "KD2M", "KD2M-TD", "KDBN2M", "KDBN1L",
    "KDDT", "KDDT180", "KDDT200", "KDDT470", "KDDT480", "KDDT500",
    "DMX", "DM180", "DM450", "DM45", "DM40", "DM50", "DM50N", "DM500B",
    "DM300", "DM250", "DM30N", "DM126MY", "DM126LCMY", "DM205LCMY",
    "KDXDB", "KGL", "KMT", "KMD", "KHDX", "KMT470", "KMD470",
    "KTC350", "KTC450", "DRV", "DRV450", "KDG",
    "KDXL1", "KDXL2", "KDXDB-G", "KDXL1-G",
    "KDV180DB", "KDV200DB", "KDV230DB", "KDV250DB", "KDV380DB", "KDV400DB",
    "KDV470DB", "KDV480DB", "KDV500DB", "KDV500DB-T",
    "KDV180L1", "KDV200L1", "KDV230L1", "KDV250L1", "KDV380L1", "KDV400L1",
    "KDV470L1", "KDV480L1", "KDV500L1",
    "KDG380", "KDG470", "KHD230", "KHD250", "KHD470", "KHD500",
    "KGL250", "KGL500-T", "KGLHG180", "KMT380", "KVGHG200", "KVHHG200",
    "PLT-DB", "PLTL", "HQT", "KTC",
}


def register_khachhang_commands(client):
    if not GROUP_KHACHHANG_ID:
        log.warning("GROUP_KHACHHANG_ID not configured — khachhang commands disabled")
        return

    log.info("khachhang commands listening on chat %d", GROUP_KHACHHANG_ID)
    db_conn = _get_connection()

    # ── Product code price lookup ────────────────────────────────────
    @client.on(events.NewMessage(chats=GROUP_KHACHHANG_ID))
    async def on_price_lookup(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return

        text = (msg.text or "").strip()
        parts = text.split()
        if len(parts) != 1:
            return

        code = parts[0].upper()
        if code in {"?", "GETJSON", "SP", "AP", "DP", "NEWKH", "NEW", "EDITKH",
                    "GET", "ADD", "CLEAR", "LINK", "UPDATE", "SHOW", "DELETE"}:
            return
        if code not in VALID_PRODUCT_CODES:
            return

        thread_id = msg.reply_to_top_id or msg.reply_to_msg_id
        if not thread_id:
            await client.send_message(
                msg.chat_id,
                "❌ Không thể xác định khách hàng cho cuộc trò chuyện này.",
                reply_to=msg.id,
            )
            return

        try:
            # Customer firebase_key is the thread_id in this group
            customer = get_customer_by_key(db_conn, str(thread_id))
            if not customer:
                await client.send_message(
                    msg.chat_id,
                    "❌ Không tìm thấy thông tin khách hàng.",
                    reply_to=msg.id,
                )
                return

            price_list = get_customer_price_list(db_conn, str(thread_id))
            price = price_list.get(code)

            if price:
                reply_text = f"Giá: <b>{int(price):,}</b>"
                await client.send_message(
                    msg.chat_id, reply_text, reply_to=msg.id, parse_mode="html"
                )
            else:
                await client.send_message(
                    msg.chat_id,
                    f"Không tìm thấy giá cho sản phẩm <b>{code}</b>.",
                    reply_to=msg.id,
                    parse_mode="html",
                )
        except Exception as e:
            log.error("Price lookup error: %s", e, exc_info=True)
            await client.send_message(
                msg.chat_id,
                "❌ Đã xảy ra lỗi khi tra cứu giá sản phẩm.",
                reply_to=msg.id,
            )

    # ── Personal price setting ─────────────────────────────────────────
    @client.on(events.NewMessage(chats=GROUP_KHACHHANG_ID))
    async def on_set_price(event):
        msg = event.message
        if isinstance(msg, MessageService):
            return

        text = (msg.text or "").strip()
        parts = text.split()
        if len(parts) != 2:
            return

        code, price_str = parts[0].upper(), parts[1]
        if code not in VALID_PRODUCT_CODES:
            return
        if not re.match(r"^\d+$", price_str):
            return
        price = int(price_str)
        if price <= 0:
            return

        thread_id = msg.reply_to_top_id or msg.reply_to_msg_id
        if not thread_id:
            await client.send_message(
                msg.chat_id,
                "❌ Không thể xác định khách hàng cho cuộc trò chuyện này.",
                reply_to=msg.id,
            )
            return

        try:
            customer = get_customer_by_key(db_conn, str(thread_id))
            if not customer:
                await client.send_message(
                    msg.chat_id,
                    "❌ Không tìm thấy thông tin khách hàng.",
                    reply_to=msg.id,
                )
                return

            # Update personal_price_list
            personal = customer.get("personal_price_list") or {}
            personal[code] = price
            customer["personal_price_list"] = personal

            ok, _ = update_customer(db_conn, str(thread_id), customer)
            if ok:
                await client.send_message(
                    msg.chat_id,
                    f"Đã cập nhật giá riêng cho sản phẩm <b>{code}</b> "
                    f"thành <b>{price:,}</b>.",
                    reply_to=msg.id,
                    parse_mode="html",
                )
            else:
                await client.send_message(
                    msg.chat_id,
                    "❌ Lỗi lưu giá riêng.",
                    reply_to=msg.id,
                )
        except Exception as e:
            log.error("Set price error: %s", e, exc_info=True)
            await client.send_message(
                msg.chat_id,
                "❌ Đã xảy ra lỗi khi cập nhật giá sản phẩm.",
                reply_to=msg.id,
            )
