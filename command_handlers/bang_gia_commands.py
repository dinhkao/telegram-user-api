"""Bảng giá (price-list) group bot — ported from node bots/groupBangGia.js.

SQLite-native (bang_gia_store). Each forum topic in the group is a
price-list "slip" keyed by thread_id: `new` creates a topic + slip,
`fix <name>` renames it, `copy` prints the `get_price_list <thread_id>`
helper command, `show` lists current prices, and `<SP> [price]` either
sets or queries a single product's price.
"""
from __future__ import annotations

import logging
import os
import random
import sqlite3

from telethon import events
from telethon.tl.types import MessageService
from telethon.tl.functions.messages import CreateForumTopicRequest, EditForumTopicRequest

from bang_gia_store import (
    create_bang_gia_table,
    migrate_bang_gia_table,
    get_slip,
    upsert_slip,
    set_name,
    set_price,
)

from .thread_utils import extract_thread_id

log = logging.getLogger("bang_gia")
GROUP_BANG_GIA_ID = int(os.getenv("GROUP_BANG_GIA_ID", "-1002373184927"))
from utils.paths import SHARED_DB_PATH
from utils.db import get_connection


def _conn():
    return get_connection()


# ─── number formatting (node `toVND()` = Number(n).toLocaleString() + "đ") ──
def _to_vnd(n) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 0
    return f"{n:,}".replace(",", ".") + "đ"


def _price_list_view(price_list: dict) -> str:
    return "\n".join(f"{k} {_to_vnd(v)}" for k, v in price_list.items())


async def _create_forum_topic(client, chat_id: int, title: str) -> int | None:
    try:
        result = await client(CreateForumTopicRequest(
            peer=chat_id, title=title, random_id=random.randrange(-2**63, 2**63),
        ))
        for upd in getattr(result, "updates", []) or []:
            m = getattr(upd, "message", None)
            if m is not None and getattr(m, "id", None):
                return m.id
    except Exception as e:  # noqa: BLE001
        log.error("create_forum_topic failed: %s", e)
    return None


def register_bang_gia_commands(client):
    conn = _conn()
    create_bang_gia_table(conn)
    migrate_bang_gia_table(conn)
    log.info("bang_gia handler listening on group %d. DB: %s", GROUP_BANG_GIA_ID, SHARED_DB_PATH)

    async def reply(msg, text, parse_mode=None):
        await client.send_message(msg.chat_id, text, reply_to=msg.id, parse_mode=parse_mode)

    @client.on(events.NewMessage(chats=GROUP_BANG_GIA_ID))
    async def on_group_msg(event):
        msg = event.message
        if isinstance(msg, MessageService) or not msg.text:
            return
        text = msg.text.strip()
        low = text.lower()

        # new — create a fresh price-list topic
        if low == "new":
            thread_id = await _create_forum_topic(client, GROUP_BANG_GIA_ID, "bang gia moi")
            if not thread_id:
                await reply(msg, "❌ Không thể tạo topic mới")
                return
            upsert_slip(conn, thread_id, name="bang gia moi", price_list={})
            await client.send_message(
                GROUP_BANG_GIA_ID, f"✅ Đã tạo bảng giá mới (ID: {thread_id})", reply_to=thread_id,
            )
            return

        # fix <new name> — rename the current topic
        if low.startswith("fix"):
            thread_id = extract_thread_id(msg)
            if not thread_id:
                return
            new_name = text[3:].strip()
            set_name(conn, thread_id, new_name)
            try:
                await client(EditForumTopicRequest(peer=GROUP_BANG_GIA_ID, topic_id=thread_id, title=new_name))
            except Exception as e:  # noqa: BLE001
                log.error("edit_forum_topic failed thread=%s: %s", thread_id, e)
            await reply(msg, f"✅ Đã đổi tên: {new_name}")
            return

        thread_id = extract_thread_id(msg)
        if not thread_id:
            return  # copy / show / SP commands operate on a slip

        # copy — print the get_price_list helper command
        if low == "copy":
            await reply(msg, f"`get_price_list {thread_id}`", parse_mode="md")
            return

        # show — list current price-list entries
        if low == "show":
            price_list = get_slip(conn, thread_id) or {}
            price_list = price_list.get("price_list") or {}
            if not price_list:
                await reply(msg, "Chưa có giá trong bảng này.")
                return
            await reply(msg, f"Bảng giá hiện tại:\n{_price_list_view(price_list)}")
            return

        # <SP> <price> — set price, or <SP> alone — query price
        parts = text.split()
        cmd = parts[0].upper()
        maybe_price = parts[1] if len(parts) > 1 else None
        price = int(maybe_price) if maybe_price and maybe_price.isdigit() else None

        if price and price > 0:
            price_list = set_price(conn, thread_id, cmd, price)
            await reply(msg, f"Cập nhật thành công, bảng giá hiện tại:\n{_price_list_view(price_list)}")
        else:
            slip = get_slip(conn, thread_id) or {}
            price_list = slip.get("price_list") or {}
            current = price_list.get(cmd)
            if current:
                await reply(msg, f"{cmd}: {_to_vnd(current)}")
            else:
                await reply(msg, f"{cmd} chưa có giá")
