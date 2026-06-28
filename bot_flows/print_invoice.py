"""bot_don_hang/flows/print_invoice.py — Print giao invoice flow."""
from bot_core import config, db, keyboards
from bot_core.utils import post_json
from bot_core.store import reset_timer
from ._helpers import log, ORDER_API_BASE


async def handle_get_html(bot, event, s):
    """Check invoice and prompt for print confirmation (same as old Node.js bot)."""
    has_kv = bool(s.kv_invoice_id)
    if not has_kv:
        order = db.get_order(s.order_id)
        if order:
            has_kv = bool(order.get("kiotvietInvoiceID") or order.get("kiotviet_invoice_id"))
    if not has_kv:
        await event.reply("Đơn hàng chưa có hóa đơn để in, không thể in")
        reset_timer(s.chat_id)
        return
    s.confirm_print = {"active": True}
    await event.reply(
        "Bạn có chắc chắn muốn in hóa đơn này không? Lưu ý chỉ in khi đi giao hàng, không in để sẵn!",
        buttons=keyboards.build_confirm_keyboard(),
    )
    reset_timer(s.chat_id)


async def handle_confirm_print_text(bot, event, s, text):
    """Handle print confirmation: call print-giao API (same as old Node.js bot)."""
    txt = text.strip().lower()
    if txt == "có":
        s.confirm_print = None
        caption = "Đã gửi lệnh in hoá đơn"
        if not s.thread_id:
            await event.reply("Không lấy được thread_id để in hoá đơn")
            from bot_handlers import send_help
            await send_help(bot, s.chat_id, s)
            return
        try:
            await event.reply("Đang in hóa đơn giao hàng...")
            resp = await post_json(
                f"{ORDER_API_BASE}/api/order/print-giao",
                {"thread_id": s.thread_id, "channel_id": config.GROUP_CHAT_ID},
            )
            if resp and resp.get("ok"):
                await event.reply("Đã gửi lệnh in: 2 hóa đơn (không QR) + Phiếu giao hàng.")
                caption = "Đã gửi lệnh in: 2 hóa đơn (không QR) + Phiếu giao hàng."
            else:
                await event.reply("Đã gửi lệnh in.")
                caption = "Đã gửi lệnh in."
        except Exception as e:
            err_text = f"In thất bại: {e}"
            log.error("print-giao error: %s", e)
            await event.reply(err_text)
            caption = err_text
        # Refresh main keyboard
        try:
            fresh = db.get_order(s.order_id)
            if fresh:
                s.task_status = fresh.get("task_status")
        except Exception:
            pass
        from bot_handlers import send_help
        await send_help(bot, s.chat_id, s, caption=caption)
        return
    if txt == "không":
        s.confirm_print = None
        from bot_handlers import send_help
        await send_help(bot, s.chat_id, s)
        return
    # Re-prompt
    await event.reply(
        "Bạn có chắc chắn muốn in hóa đơn này không? Lưu ý chỉ in khi đi giao hàng, không in để sẵn!",
        buttons=keyboards.build_confirm_keyboard(),
    )
