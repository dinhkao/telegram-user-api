from __future__ import annotations

import logging
import os

log = logging.getLogger("customer_notify")
ORDER_GROUP_ID = int(os.getenv("ORDER_GROUP_ID", "-1002124542200"))


def send_payment_notification(client, kh_id: str, thread_id: int, amount: int, method: str,
                              order_text: str, old_debt: int | None = None, new_debt: int | None = None) -> None:
    if not client or not kh_id:
        return
    order_group_str = str(ORDER_GROUP_ID)
    internal_id = order_group_str[4:] if order_group_str.startswith("-100") else str(abs(ORDER_GROUP_ID))
    order_topic_url = f"https://t.me/c/{internal_id}/{thread_id}"
    title = _esc(order_text) if order_text else f"Đơn hàng #{thread_id}"
    method_label = "TM" if method.lower() == "cash" else "CK"
    method_icon = "💵" if method.lower() == "cash" else "💳"
    if old_debt is not None and new_debt is not None:
        delta = new_debt - old_debt
        sign = "+" if delta >= 0 else ""
        note = (f"{method_icon} Thanh toán ({method_label}) {amount:,}đ cho "
                f'<a href="{order_topic_url}">{title}</a>\nNợ cũ: {old_debt:,}đ\n'
                f"Nợ mới: {new_debt:,}đ ({sign}{delta:,}đ)")
    else:
        note = f"{method_icon} Đã tạo thanh toán ({method_label}) {amount:,}đ cho <a href=\"{order_topic_url}\">{title}</a>"
    try:
        client.loop.create_task(client.send_message(ORDER_GROUP_ID, note, parse_mode="html", message_thread_id=int(kh_id)))
        log.info("Payment notification sent to customer topic %s", kh_id)
    except Exception as e:
        log.warning("Failed to notify customer topic %s: %s", kh_id, e)


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))
