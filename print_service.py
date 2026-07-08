"""print_service.py — Shared print logic used by both Telethon handler and HTTP API."""

import json
import logging
import os

log = logging.getLogger("print_service")


async def execute_print_giao(conn, order, user_id=None) -> dict:
    """Execute print-giao: 2 invoices (no QR) + 1 delivery ticket.

    Args:
        conn: SQLite connection
        order: order dict from DB
        user_id: Telegram user ID who initiated print

    Returns:
        {"ok": True} on success, {"error": "..."} on failure
    """
    # Ràng buộc quy trình: giao hàng xong mới in HĐ giao (toggle Cài đặt webapp)
    from order_store.guards import print_giao_block_reason
    _reason = print_giao_block_reason(order or {})
    if _reason:
        return {"error": _reason, "blocked": True}
    from order_db import get_customer_by_key
    from inhoadon import generate_invoice_html
    from delivery_ticket import _enqueue_html_for_print, generate_delivery_ticket_html

    thread_id = order.get("thread_id")

    invoice_id = order.get("kiotvietInvoiceID")
    if not invoice_id:
        return {"error": "No KiotViet invoice to print"}

    # Customer
    kh_id_fb = order.get("khach_hang_id") or order.get("khID")
    customer_name = "Khách hàng"
    if kh_id_fb:
        customer = get_customer_by_key(conn, str(kh_id_fb))
        if customer:
            customer_name = customer.get("name", "Khách hàng")

    order_text = order.get("text", "")

    # Invoice HTML (no QR, 2 copies)
    snapshot_debt = order.get("invoice_debt_snapshot", 0)
    invoice_html = generate_invoice_html(invoice_id, debt=snapshot_debt, hints={
        "expectedVAT": int(order.get("vat", 0)),
        "expectedPVC": int(order.get("pvc", 0)),
        "customerNameOverride": customer_name,
        "disableQR": True,
    })
    await _enqueue_html_for_print(invoice_html, copies=2)

    # Nộp tiền task URL
    nop_tien_topic_url = ""
    try:
        cur = conn.execute(
            "SELECT json FROM tasks WHERE json_extract(json, '$.dhThreadID') = ? "
            "AND json_extract(json, '$.taskType') = 'nop_tien' LIMIT 1",
            (thread_id,)
        )
        task_row = cur.fetchone()
        if task_row:
            task_data = json.loads(task_row["json"])
            task_thread_id = task_data.get("threadID")
            if task_thread_id:
                task_group_id = int(os.getenv("TASK_GROUP_ID", "-1002574612166"))
                internal_id = str(task_group_id)[4:] if str(task_group_id).startswith("-100") else str(abs(task_group_id))
                nop_tien_topic_url = f"tg://privatepost?channel={internal_id}&post={task_thread_id}"
    except Exception as e:
        log.warning("print-giao: failed to get nop_tien task URL: %s", e)

    # Delivery ticket (1 copy)
    printed_by = str(user_id) if user_id else "Hệ thống"
    delivery_html = generate_delivery_ticket_html(
        thread_id=thread_id,
        customer_name=customer_name,
        order_text=order_text,
        printed_by=printed_by,
        nop_tien_topic_url=nop_tien_topic_url,
    )
    await _enqueue_html_for_print(delivery_html, copies=1)

    return {"ok": True}
