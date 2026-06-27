from __future__ import annotations

import logging
import os

from order_db import get_order_by_thread_id

from .thread_utils import extract_thread_id

log = logging.getLogger("order_commands")
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))
TASK_DONE_COMMANDS = {"ban": ("ban_hd", "✅ {user} đã đánh dấu Bán HĐ"), "soan": ("soan_hang", "✅ {user} đã đánh dấu Soạn hàng"), "giao": ("giao_hang", "✅ {user} đã đánh dấu Giao hàng"), "nop tien": ("nop_tien", "✅ {user} đã đánh dấu Nộp tiền"), "nop": ("nop_tien", "✅ {user} đã đánh dấu Nộp tiền"), "nhan tien": ("nhan_tien", "✅ {user} đã đánh dấu Nhận tiền"), "nhan": ("nhan_tien", "✅ {user} đã đánh dấu Nhận tiền"), "xuat hd roi": ("xuat_hd", "✅ {user} đã đánh dấu Xuất HĐ"), "xuat hd": ("xuat_hd", "✅ {user} đã đánh dấu Xuất HĐ")}
CLEAR_COMMANDS = {"clear soan": "soan_hang", "clear soan hang": "soan_hang", "clear giao": "giao_hang", "clear giao hang": "giao_hang", "clear nop": "nop_tien", "clear nop tien": "nop_tien", "clear nhan": "nhan_tien", "clear nhan tien": "nhan_tien"}
CLEAR_REPLIES = {"soan_hang": "♻️ Đã đặt lại trạng thái Soạn hàng", "giao_hang": "♻️ Đã đặt lại trạng thái Giao hàng", "nop_tien": "♻️ Đã đặt lại trạng thái Nộp tiền", "nhan_tien": "♻️ Đã đặt lại trạng thái Nhận tiền"}
SKIP_COMMANDS = {"skip nop tien": "nop_tien"}


async def resolve_user_name(client, sender_id):
    if not sender_id:
        return "Hệ thống"
    try:
        entity = await client.get_entity(sender_id)
        first, last = getattr(entity, "first_name", None), getattr(entity, "last_name", None)
        return f"{first} {last}".strip() if first and last else first or str(sender_id)
    except Exception:
        return str(sender_id)


def notify_refresh(client, db_conn, thread_id: int):
    try:
        order = get_order_by_thread_id(db_conn, thread_id)
        if not order:
            return
        row = db_conn.execute("SELECT channel_id, message_id FROM orders WHERE thread_id = ? AND deleted_at IS NULL", (thread_id,)).fetchone()
        if row and row["channel_id"] and row["message_id"]:
            from order_commands_v3 import _refresh_order_message

            client.loop.create_task(_refresh_order_message(client, db_conn, thread_id, row["channel_id"], row["message_id"]))
        from firebase_sync import set_order as fb_set_order

        try:
            fb_set_order(thread_id, order)
        except Exception:
            pass
    except Exception as e:
        log.warning("Failed to notify refresh: %s", e)

