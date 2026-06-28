"""bot_flows/rename_giao.py — Rename order + giao hàng confirm flows."""
from bot_core import config, db, keyboards
from bot_core.utils import post_json, is_cancel, _norm, mark_task
from bot_core.store import reset_timer
from ._helpers import log, ORDER_API_BASE

async def handle_rename_text(bot, event, s, text):
    if not s.awaiting_rename:
        return
    if is_cancel(text) or _norm(text) == "quay lai, khong sua nua":
        s.awaiting_rename = False
        from bot_handlers import send_help
        await send_help(bot, s.chat_id, s)
        return
    known = {"ban hd", "soan hang", "giao hang", "nop tien", "nhan tien",
        "xem hoa don", "in hoa don giao", "xem thong tin", "sua ten don hang",
        "huy ban", "huy soan", "huy giao", "huy nop", "huy nhan",
        "quay lai, khong sua nua"}
    if _norm(text) in known or text.startswith("✅") or text.startswith("/"):
        return
    s.awaiting_rename = False
    if not s.thread_id:
        await event.reply(f"Không lấy được thread_id cho đơn {s.order_id}.")
        return
    await event.reply("Đang cập nhật tên đơn hàng...")
    try:
        await post_json(f"{ORDER_API_BASE}/api/order/fix", {
            "thread_id": s.thread_id, "text": text, "user_id": s.user_id})
        s.last_text = text
        from bot_handlers import send_help
        await send_help(bot, s.chat_id, s)
        await event.reply("Đã cập nhật tên đơn hàng")
    except Exception as e:
        log.error("rename error: %s", e)
        await event.reply(f"Cập nhật tên thất bại: {e}")
    reset_timer(s.chat_id)

async def start_giao_confirm(bot, event, s):
    s.confirm_giao = {"active": True}
    await event.reply(
        "Bạn có chắc chắn muốn giao đơn hàng này không?",
        buttons=keyboards.build_confirm_keyboard())
    reset_timer(s.chat_id)

async def handle_giao_confirm_text(bot, event, s, text):
    if not s.confirm_giao or not s.confirm_giao.get("active"):
        return
    txt = text.strip().lower()
    if txt == "có":
        s.confirm_giao = None
        if not s.thread_id:
            await event.reply(f"Không lấy được thread_id cho đơn {s.order_id}.")
            return
        ok = await mark_task(s, "giao", s.user_id)
        if ok:
            await event.reply("✅ Đã đánh dấu giao hàng.")
            from bot_handlers import send_help
            await send_help(bot, s.chat_id, s)
        else:
            await event.reply("Thao tác thất bại.")
        return
    if txt == "không":
        s.confirm_giao = None
        from bot_handlers import send_help
        await send_help(bot, s.chat_id, s)
        return
    await event.reply("Bạn có chắc chắn muốn giao đơn hàng này không?",
        buttons=keyboards.build_confirm_keyboard())
    reset_timer(s.chat_id)
