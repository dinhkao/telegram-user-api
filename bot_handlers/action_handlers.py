"""bot_handlers/action_handlers.py — Handle action buttons & flow delegation."""
import logging
from bot_core import config, db, store
from bot_core.utils import mark_task
import bot_flows as flows
from .session import send_help

log = logging.getLogger("bot.handlers")

async def handle_action(bot, event, s, text, uid):
    from bot_core import keyboards
    from bot_core.utils import is_cancel
    if is_cancel(text):
        s.edit_invoice = s.confirm_kv = s.confirm_payment = None
        s.confirm_giao = s.confirm_print = s.pay_flow = s.nop_wizard = None
        s.awaiting_rename = False
        await event.reply("Đã huỷ thao tác.")
        try:
            await send_help(bot, event.chat_id, s)
        except Exception:
            pass
        return True
    if text.strip().lower() == "quay lại":
        await send_help(bot, event.chat_id, s)
        return True
    if text.strip().lower() == "tạo hóa đơn kiotviet luôn!":
        if not config.is_admin(uid):
            await event.reply("Chức năng chỉ dành cho admin.")
            return True
        s.confirm_kv = {"active": True}
        await event.reply("Bạn có chắc chắn tạo hóa đơn Kiotviet?",
            buttons=keyboards.build_kv_confirm_keyboard())
        return True
    clear_map = {"Huỷ bán": "ban_hd", "Huỷ soạn": "soan_hang",
        "Huỷ giao": "giao_hang", "Huỷ nộp": "nop_tien", "Huỷ nhận": "nhan_tien"}
    if text in clear_map:
        await _handle_clear(bot, s, uid, clear_map[text], event)
        return True
    action_map = {"Bán HD": "ban", "Soạn hàng": "soan", "Giao hàng": "giao",
        "Nộp tiền": "nop-tien", "Nhận tiền": "nhan-tien"}
    if text in action_map:
        await _handle_action_button(bot, event, s, uid, action_map[text], text)
        return True
    return False

async def _handle_clear(bot, s, uid, key, event):
    entry = (s.task_status or {}).get(key) or {}
    if not entry.get("done"):
        await event.reply("Thao tác nãy chưa được đánh dấu hoàn thành.")
        return
    if str(uid) != str(entry.get("by") or ""):
        by_name = config.name_of_user_id(entry.get("by")) or "người khác"
        await event.reply(f"Chỉ {by_name} mới có thể huỷ.")
        return
    if s.thread_id:
        from bot_core.utils import post_json
        from bot_flows._helpers import ORDER_API_BASE
        try:
            await post_json(f"{ORDER_API_BASE}/api/order/{s.thread_id}/task_status/clear", {"type": key})
            fresh = db.get_order_by_thread(s.thread_id)
            if fresh:
                s.task_status = fresh.get("task_status")
            await send_help(bot, event.chat_id, s)
        except Exception as e:
            await event.reply(f"Huỷ thất bại: {e}")

async def _handle_action_button(bot, event, s, uid, step, text):
    if step == "ban":
        await event.reply("Bấm vào Xem hóa đơn → Cập nhật hóa đơn")
        return
    if step == "nop-tien":
        await flows.start_nop_wizard(bot, event, s)
        return
    if step == "nhan-tien":
        await flows.start_payment_flow(bot, event, s)
        return
    if not s.thread_id:
        await event.reply("Không lấy được thread_id.")
        return
    ok = await mark_task(s, step, uid)
    if ok:
        await event.reply(f"✅ Đã đánh dấu {text}.")
        await send_help(bot, event.chat_id, s)
    else:
        await event.reply(f"Thao tác thất bại.")
