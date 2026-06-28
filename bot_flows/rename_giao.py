"""bot_don_hang/flows/rename_giao.py — Rename order + giao hàng confirm flows."""
from bot_core import config, db, keyboards
from bot_core.utils import post_json, is_cancel, _norm
from bot_core.store import reset_timer
from ._helpers import log, ORDER_API_BASE


async def handle_rename_text(bot, event, s, text):
    """Handle text input during rename order flow."""
    if not s.awaiting_rename:
        return
    if is_cancel(text) or _norm(text) == "quay lai, khong sua nua":
        s.awaiting_rename = False
        from bot_core.handlers import send_help
        await send_help(bot, s.chat_id, s)
        return

    # Check if it's a known command/label — if so, ignore
    known = {
        "ban hd", "soan hang", "giao hang", "nop tien", "nhan tien",
        "xem hoa don", "in hoa don giao", "xem thong tin", "sua ten don hang",
        "huy ban", "huy soan", "huy giao", "huy nop", "huy nhan",
        "quay lai, khong sua nua",
    }
    if _norm(text) in known or text.startswith("✅") or text.startswith("/"):
        return

    # Treat this text as the new order title
    s.awaiting_rename = False
    thread_id = s.thread_id
    if not thread_id:
        await event.reply(f"Không lấy được thread_id cho đơn {s.order_id}.")
        return
    try:
        await event.reply("Đang cập nhật tên đơn hàng...")
        await post_json(f"{ORDER_API_BASE}/api/order/fix", {
            "thread_id": thread_id,
            "text": text,
            "user_id": s.user_id,
        })
        s.last_text = text
        from bot_core.handlers import send_help
        await send_help(bot, s.chat_id, s)
        await event.reply("Đã cập nhật tên đơn hàng")
    except Exception as e:
        log.error("rename error: %s", e)
        await event.reply(f"Cập nhật tên thất bại: {e}")
    reset_timer(s.chat_id)


async def start_giao_confirm(bot, event, s):
    """Start giao hàng confirmation dialog."""
    s.confirm_giao = {"active": True}
    await event.reply(
        "Bạn có chắc chắn muốn giao đơn hàng này không? Lưu ý chỉ bấm giao khi chuẩn bị đi giao, không bấm để sẵn!",
        buttons=keyboards.build_confirm_keyboard(),
    )
    reset_timer(s.chat_id)


async def handle_giao_confirm_text(bot, event, s, text):
    """Handle text input during giao hàng confirmation."""
    if not s.confirm_giao or not s.confirm_giao.get("active"):
        return
    txt = text.strip().lower()
    if txt == "có":
        s.confirm_giao = None
        # Actually perform giao
        if not s.thread_id:
            await event.reply(f"Không lấy được thread_id cho đơn {s.order_id}.")
            return
        try:
            await post_json(f"{ORDER_API_BASE}/api/order/giao", {"thread_id": s.thread_id, "user_id": s.user_id})
            try:
                fresh = db.get_order(s.order_id)
                if fresh:
                    s.task_status = fresh.get("task_status")
            except Exception:
                pass
            await event.reply("✅ Đã đánh dấu giao hàng.")
            from bot_core.handlers import send_help
            await send_help(bot, s.chat_id, s)
        except Exception as e:
            log.error("giao error: %s", e)
            await event.reply(f"Thao tác thất bại: {e}")
        return
    if txt == "không":
        s.confirm_giao = None
        from bot_core.handlers import send_help
        await send_help(bot, s.chat_id, s)
        return
    await event.reply(
        "Bạn có chắc chắn muốn giao đơn hàng này không? Lưu ý chỉ bấm giao khi chuẩn bị đi giao, không bấm để sẵn!",
        buttons=keyboards.build_confirm_keyboard(),
    )
    reset_timer(s.chat_id)
