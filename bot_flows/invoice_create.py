"""bot_don_hang/flows/invoice_create.py — Create KiotViet invoice (Tạo HD)."""
import logging
import os
import tempfile
import time

from telethon import Button

from bot_core import config, db, keyboards
from bot_core.utils import post_json, esc_html
from bot_core.store import reset_timer
from ._helpers import log, ORDER_API_BASE


def _save_order_field(order_id: str, field: str, value):
    """Save a single field to order JSON in SQLite."""
    import json
    conn = db._conn()
    row = conn.execute(
        "SELECT json FROM orders WHERE firebase_key = ? AND deleted_at IS NULL",
        (order_id,),
    ).fetchone()
    if not row:
        return
    data = json.loads(row[0])
    data[field] = value
    conn.execute(
        "UPDATE orders SET json = ?, updated_at = ? WHERE firebase_key = ?",
        (json.dumps(data, ensure_ascii=False), int(time.time() * 1000), order_id),
    )
    conn.commit()


async def handle_tao_hd(bot, event, s):
    if not s.thread_id:
        await event.reply(f"Không lấy được thread_id cho đơn {s.order_id}.")
        return
    if not config.is_admin(s.user_id):
        await event.reply("Chức năng chỉ dành cho admin (Duy, Trang).")
        return
    if s.kv_invoice_id:
        await event.reply("❌ Đơn hàng nãy đã được tạo hóa đơn Kiotviet rồi, không thể tạo thêm!")
        return
    # Double-check DB
    order = db.get_order(s.order_id)
    if order and (order.get("kiotvietInvoiceID") or order.get("kiotviet_invoice_id")):
        await event.reply("❌ Đơn hàng nấy đã được tạo hóa đơn Kiotviet rồi, không thể tạo thêm!")
        return

    # Validate prerequisites (same as telegram-user-api on_tao_hd)
    invoice = order.get("invoice") or order.get("invoice_items") or []
    if not invoice:
        await event.reply("❌ Không có sản phẩm nào trong đơn hàng. Dùng 'Cập nhật hóa đơn' để thêm sản phẩm.")
        return

    kh_id_fb = order.get("khach_hang_id") or order.get("khID")
    if not kh_id_fb:
        await event.reply("❌ Đơn hàng chưa có khách hàng. Gán khách hàng trước.")
        return

    customer = db.get_customer_by_key(str(kh_id_fb))
    if not customer or not customer.get("kh_id"):
        await event.reply("❌ Không tìm thấy ID KiotViet của khách hàng.")
        return

    kv_id = customer["kh_id"]
    discount = int(order.get("discount", 0))
    pvc = int(order.get("pvc", 0))
    vat = int(order.get("vat", 0))

    proc_msg = await event.reply("⏳ Đang tạo hóa đơn KiotViet......")

    # Run blocking KiotViet calls on a thread pool (parallel like order_commands_v3)
    import asyncio
    from kiotviet import get_customer_debt_kv, create_kiotviet_invoice, get_invoice_detail as _get_invoice_detail
    loop = asyncio.get_running_loop()

    debt_future = loop.run_in_executor(None, get_customer_debt_kv, kv_id)
    result = await loop.run_in_executor(
        None,
        lambda: create_kiotviet_invoice(
            customer_id=kv_id,
            invoice_items=invoice,
            discount=discount,
            pvc=pvc,
            vat=vat,
        )
    )

    # Collect debt result (best-effort, fetched in parallel)
    old_debt = None
    try:
        det = await debt_future
        old_debt = det.get("debt")
    except Exception as e:
        log.warning("Could not fetch old debt for customer %d: %s", kv_id, e)

    if not result:
        await proc_msg.edit("❌ Tạo hóa đơn KiotViet thất bại!")
        return

    invoice_code = result.get("code", "N/A")
    invoice_id = result.get("id")

    # Save invoice ID + metadata to SQLite (same as telegram-user-api)
    snapshot_debt = old_debt if old_debt is not None else 0
    _save_order_field(s.order_id, "kiotvietInvoiceID", invoice_id)
    _save_order_field(s.order_id, "kiotvietInvoiceCode", invoice_code)
    _save_order_field(s.order_id, "nguoi_tao_HD", [s.user_id or 1809874974])
    _save_order_field(s.order_id, "invoice_debt_snapshot", snapshot_debt)
    if old_debt is not None:
        _save_order_field(s.order_id, "khDebt", old_debt)
    s.kv_invoice_id = str(invoice_id)

    # Auto-complete ban_hd and mirror via API (same as telegram-user-api)
    try:
        await post_json(f"{ORDER_API_BASE}/api/order/ban", {"thread_id": s.thread_id, "user_id": s.user_id})
        fresh = db.get_order(s.order_id)
        if fresh:
            s.task_status = fresh.get("task_status")
    except Exception as e:
        log.warning("ban_hd API call failed: %s", e)

    # Edit processing message to success (same as telegram-user-api)
    await proc_msg.edit(
        f"✅ Tạo hóa đơn KiotViet thành công! {invoice_code}\n✅ Đã đánh dấu Bán HĐ hoàn thành"
    )

    # Generate invoice HTML and send as file (same as telegram-user-api)
    try:
        from inhoadon import generate_invoice_html
        inv_detail = _get_invoice_detail(invoice_id)
        if inv_detail:
            html = generate_invoice_html(inv_detail, snapshot_debt, {
                "expectedVAT": vat,
                "expectedPVC": pvc,
                "orderTopicUrl": f"tg://privatepost?channel={str(config.GROUP_CHAT_ID).replace('-100', '')}&post={s.thread_id}",
                "customerNameOverride": customer.get("name"),
                "disableQR": True,
            })
        else:
            html = f"""<html><body>
<h1>Hóa đơn #{invoice_code}</h1>
<p>Khách: {esc_html(customer.get('name', ''))}</p>
<p>ID: {invoice_id}</p>
</body></html>"""
        fn = f"invoice_{s.thread_id}_{int(time.time())}.html"
        file_path = os.path.join(tempfile.gettempdir(), fn)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html)
        await bot.send_file(
            s.chat_id,
            file_path,
            caption=f"🧾 Hóa đơn {invoice_code} — {customer.get('name', '')}",
            force_document=True,
        )
        try:
            os.unlink(file_path)
        except OSError:
            pass

        # Render HTML → PNG and send photo directly via bot (no user-account/firebase dep)
        try:
            from bot_core.html_to_png import render_and_send_html
            await render_and_send_html(
                bot, html, s.chat_id, reply_to=s.thread_id,
                caption=f"🧾 Hóa đơn {invoice_code} — {customer.get('name', '')}",
            )
        except Exception as e:
            log.warning("Failed to render invoice PNG: %s", e)
    except Exception as e:
        log.error("Invoice HTML generation failed: %s", e)
        await bot.send_message(s.chat_id, f"✅ Đã tạo hóa đơn KiotViet: #{invoice_code} (không gửi được file HTML)")

    # Trigger order message update via API
    try:
        await post_json(f"{ORDER_API_BASE}/api/order/refresh-view", {"thread_id": s.thread_id})
    except Exception as e:
        log.warning("refresh-view failed: %s", e)

    reset_timer(s.chat_id)
