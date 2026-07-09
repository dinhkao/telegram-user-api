"""bot_flows/invoice_create.py — Create KiotViet invoice (Tạo HD)."""
import json, logging, time
from bot_core import config, db
from bot_core.utils import post_json
from bot_core.store import reset_timer
from ._helpers import log, ORDER_API_BASE

def _save_order_field(order_id, field, value):
    conn = db._conn()
    row = conn.execute("SELECT json FROM orders WHERE firebase_key = ? AND deleted_at IS NULL", (order_id,)).fetchone()
    if not row:
        return
    data = json.loads(row[0])
    data[field] = value
    conn.execute("UPDATE orders SET json = ?, updated_at = ? WHERE firebase_key = ?",
        (json.dumps(data, ensure_ascii=False), int(time.time() * 1000), order_id))
    conn.commit()

async def handle_tao_hd(bot, event, s):
    if not s.thread_id:
        await event.reply(f"Không lấy được thread_id cho đơn {s.order_id}.")
        return
    if not config.is_admin(s.user_id):
        await event.reply("Chức năng chỉ dành cho admin.")
        return
    if s.kv_invoice_id:
        await event.reply("❌ Đơn đã có hóa đơn Kiotviet rồi!")
        return
    order = db.get_order(s.order_id)
    if order and (order.get("kiotvietInvoiceID") or order.get("kiotviet_invoice_id")):
        await event.reply("❌ Đơn đã có hóa đơn Kiotviet rồi!")
        return
    invoice = order.get("invoice") or order.get("invoice_items") or []
    if not invoice:
        await event.reply("❌ Không có sản phẩm. Dùng 'Cập nhật hóa đơn' để thêm.")
        return
    kh_id_fb = order.get("khach_hang_id") or order.get("khID")
    if not kh_id_fb:
        await event.reply("❌ Đơn chưa có khách hàng.")
        return
    customer = db.get_customer_by_key(str(kh_id_fb))
    if not customer or not customer.get("kh_id"):
        await event.reply("❌ Không tìm thấy ID KiotViet của khách hàng.")
        return
    kv_id = customer["kh_id"]
    discount, pvc, vat = int(order.get("discount", 0)), int(order.get("pvc", 0)), int(order.get("vat", 0))
    proc_msg = await event.reply("⏳ Đang tạo hóa đơn KiotViet......")
    import asyncio
    from kiotviet import get_customer_debt_kv, create_kiotviet_invoice
    loop = asyncio.get_running_loop()
    debt_future = loop.run_in_executor(None, get_customer_debt_kv, kv_id)
    def _create():
        from order_db import _get_connection
        from product_store import kv_ids_for_items
        return create_kiotviet_invoice(
            customer_id=kv_id, invoice_items=invoice, discount=discount, pvc=pvc, vat=vat,
            kv_ids=kv_ids_for_items(_get_connection(), invoice))
    result = await loop.run_in_executor(None, _create)
    old_debt = None
    try:
        old_debt = (await debt_future).get("debt")
    except Exception as e:
        log.warning("Could not fetch old debt: %s", e)
    if not result:
        await proc_msg.edit("❌ Tạo hóa đơn KiotViet thất bại!")
        return
    invoice_code, invoice_id = result.get("code", "N/A"), result.get("id")
    snapshot_debt = old_debt if old_debt is not None else 0
    for f, v in [("kiotvietInvoiceID", invoice_id), ("kiotvietInvoiceCode", invoice_code),
                 ("nguoi_tao_HD", [s.user_id or 1809874974]), ("invoice_debt_snapshot", snapshot_debt)]:
        _save_order_field(s.order_id, f, v)
    if old_debt is not None:
        _save_order_field(s.order_id, "khDebt", old_debt)
    s.kv_invoice_id = str(invoice_id)
    try:
        await post_json(f"{ORDER_API_BASE}/api/order/ban", {"thread_id": s.thread_id, "user_id": s.user_id})
        fresh = db.get_order(s.order_id)
        if fresh:
            s.task_status = fresh.get("task_status")
    except Exception as e:
        log.warning("ban_hd API call failed: %s", e)
    await proc_msg.edit(f"✅ Tạo hóa đơn KiotViet thành công! {invoice_code}\n✅ Đã đánh dấu Bán HĐ hoàn thành")
    from bot_flows.invoice_render import render_and_send_invoice, refresh_order_view
    await render_and_send_invoice(bot, event, s, invoice_id, invoice_code, customer, vat, pvc, snapshot_debt)
    await refresh_order_view(s)
    reset_timer(s.chat_id)
