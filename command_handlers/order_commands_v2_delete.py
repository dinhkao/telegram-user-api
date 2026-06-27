from __future__ import annotations

import html as _html
import logging
import os

from kiotviet import delete_invoice_kv, get_customer_debt_kv
from order_db import _save_order, clear_task_status, delete_order, get_customer_by_key, get_order_by_thread_id
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
        _, message = delete_order(db_conn, thread_id)
        await client.send_message(msg.chat_id, message, reply_to=msg.id)
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
    old_debt = None
    if kh_id_fb:
        try:
            customer = get_customer_by_key(db_conn, str(kh_id_fb))
            kv_id = customer.get("kh_id") if customer else None
            if kv_id:
                old_debt = get_customer_debt_kv(kv_id).get("debt", 0)
        except Exception:
            pass
    await status_msg.edit(f"⏳ Đang xóa hóa đơn KiotViet #{invoice_id}...")
    try:
        delete_invoice_kv(invoice_id)
    except Exception as e:
        log.error("delete_invoice_kv failed thread=%d invoice=%s: %s", thread_id, invoice_id, e)
        await status_msg.edit(f"❌ Lỗi kết nối KiotViet: {e}")
        return True
    await status_msg.edit("⏳ Đang cập nhật dữ liệu đơn hàng...")
    order.update({"kiotvietInvoiceID": None, "kiotvietInvoiceCode": None, "invoice_debt_snapshot": None, "nguoi_tao_HD": None})
    _save_order(db_conn, thread_id, order)
    clear_task_status(db_conn, thread_id, "ban_hd", user_id)
    if order.get("channel_id") and order.get("message_id"):
        await status_msg.edit("⏳ Đang làm mới tin nhắn đơn hàng...")
        await refresh_main_msg(client, db_conn, thread_id, order["channel_id"], order["message_id"])
    debt_lines = []
    if kh_id_fb:
        try:
            customer2 = get_customer_by_key(db_conn, str(kh_id_fb))
            kv_id2 = customer2.get("kh_id") if customer2 else None
            if kv_id2:
                await status_msg.edit("⏳ Đang cập nhật công nợ khách hàng...")
                new_debt = None
                for attempt in range(1, 6):
                    try:
                        new_debt = get_customer_debt_kv(kv_id2).get("debt", 0)
                    except Exception:
                        pass
                    if old_debt is None or new_debt is None or new_debt != old_debt or attempt == 5:
                        break
                    import asyncio

                    await asyncio.sleep(1.2 * attempt)
                if new_debt is not None:
                    order["khDebt"] = new_debt
                    _save_order(db_conn, thread_id, order)
                    if old_debt is not None:
                        delta = new_debt - old_debt
                        debt_lines.append(f"💰 Nợ: {old_debt:,}đ → {new_debt:,}đ ({delta:+,}đ)")
                    else:
                        debt_lines.append(f"💰 Nợ: {new_debt:,}đ")
                    order_group_str = str(ORDER_GROUP_ID)
                    internal_id = order_group_str[4:] if order_group_str.startswith("-100") else str(abs(ORDER_GROUP_ID))
                    order_topic_url = f"https://t.me/c/{internal_id}/{thread_id}"
                    title = _html.escape(str(order.get("text") or f"Đơn hàng #{thread_id}"))
                    note = f'🗑️ Xóa hoá đơn của <a href="{order_topic_url}">{title}</a>'
                    if old_debt is not None:
                        note += f"\nNợ cũ: {old_debt:,}đ\nNợ mới: {new_debt:,}đ ({delta:+,}đ)"
                    try:
                        await client.send_message(ORDER_GROUP_ID, note, parse_mode="html", message_thread_id=int(kh_id_fb))
                    except Exception as e2:
                        log.warning("Customer topic notify failed: %s", e2)
        except Exception as e3:
            log.warning("Debt update after invoice delete failed: %s", e3)
    await status_msg.edit("✅ Xóa hoá đơn KiotViet thành công!" + ("\n" + "\n".join(debt_lines) if debt_lines else ""))
    return True
