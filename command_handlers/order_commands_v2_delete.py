from __future__ import annotations

import logging
import os

from kiotviet import delete_invoice_kv, get_customer_debt_kv
from order_db import _save_order, delete_order, get_customer_by_key, get_order_by_thread_id
from order_store.tasks import set_task_status
from .order_commands_v2_delete_debt import update_debt_and_notify
from .order_commands_v2_delete_refresh import refresh_after_soft_delete
from .order_commands_v2_utils import refresh_main_msg
from .thread_utils import extract_thread_id
log = logging.getLogger("order_commands_v2")
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))

async def handle_delete(client, msg, db_conn):
    text = (msg.text or "").strip().lower()
    if text not in {"del", "del hd"}:
        return False
    thread_id = extract_thread_id(msg)
    if not thread_id:
        await client.send_message(msg.chat_id, "❌ Dùng lệnh này trong topic đơn hàng", reply_to=msg.id)
        return True
    if text == "del":
        ok, message = delete_order(db_conn, thread_id)
        await client.send_message(msg.chat_id, message, reply_to=msg.id)
        if ok:
            deleted_order = get_order_by_thread_id(db_conn, thread_id)
            if deleted_order:
                await refresh_after_soft_delete(client, db_conn, thread_id, deleted_order)
        return True
    user_id = getattr(msg, "sender_id", None)
    status_msg = await client.send_message(msg.chat_id, "⏳ Đang kiểm tra đơn hàng...", reply_to=msg.id)
    order = get_order_by_thread_id(db_conn, thread_id)
    if not order:
        await status_msg.edit("❌ Không tìm thấy đơn hàng")
        return True
    invoice_id = order.get("kiotvietInvoiceID")
    if not invoice_id:
        await status_msg.edit("❌ Đơn hàng chưa có hóa đơn KiotViet")
        return True
    kh_id_fb = order.get("khach_hang_id") or order.get("khID")
    old_debt = _fetch_old_debt(db_conn, kh_id_fb)
    await status_msg.edit(f"⏳ Đang xóa hóa đơn KiotViet #{invoice_id}...")
    ok, err = await _delete_kv_invoice(invoice_id)
    if not ok:
        await status_msg.edit(f"❌ Lỗi kết nối KiotViet: {err}")
        return True
    await status_msg.edit("⏳ Đang cập nhật dữ liệu đơn hàng...")
    _clear_invoice_fields(db_conn, thread_id, order)
    set_task_status(db_conn, thread_id, "ban_hd", user_id, done=False)
    if order.get("channel_id") and order.get("message_id"):
        await status_msg.edit("⏳ Đang làm mới tin nhắn đơn hàng...")
        await refresh_main_msg(client, db_conn, thread_id, order["channel_id"], order["message_id"])
    debt_lines = await update_debt_and_notify(client, db_conn, thread_id, order, kh_id_fb, old_debt)
    await status_msg.edit("✅ Xóa hoá đơn KiotViet thành công!" + ("\n" + "\n".join(debt_lines) if debt_lines else ""))
    return True


def _fetch_old_debt(db_conn, kh_id_fb):
    if not kh_id_fb:
        return None
    try:
        customer = get_customer_by_key(db_conn, str(kh_id_fb))
        kv_id = customer.get("kh_id") if customer else None
        if kv_id:
            return get_customer_debt_kv(kv_id).get("debt", 0)
    except Exception:
        pass
    return None


async def _delete_kv_invoice(invoice_id):
    try:
        delete_invoice_kv(invoice_id)
        return True, None
    except Exception as e:
        log.error("delete_invoice_kv failed invoice=%s: %s", invoice_id, e)
        return False, e


def _clear_invoice_fields(db_conn, thread_id, order):
    order.update({"kiotvietInvoiceID": None, "kiotvietInvoiceCode": None, "invoice_debt_snapshot": None, "nguoi_tao_HD": None})
    _save_order(db_conn, thread_id, order)