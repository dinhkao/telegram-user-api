"""bot_don_hang/handlers/media_events.py — NewMessage handler for media."""
import logging

from telethon import events

from bot_core import config, db, store
from bot_core.utils import post_json
from bot_flows import flows
from .session import send_help

log = logging.getLogger("bot.handlers")
ORDER_API_BASE = config.ORDER_API_BASE


def register_media_handlers(bot):
    @bot.on(events.NewMessage)
    async def on_media(event):
        if not event.message.media:
            return
        chat_id = event.chat_id
        uid = event.sender_id
        if not config.is_allowed(uid):
            return
        s = store.get(chat_id)
        if not s or not s.order_id:
            return

        # Nộp tiền wizard waiting for photo
        if s.nop_wizard and s.nop_wizard.get("active") and s.nop_wizard.get("step") == "wait_photo":
            handled = await flows.handle_nop_wizard_photo(bot, event, s)
            if handled:
                return

        # Forward media to group chat via user account (Telethon user API)
        try:
            caption = f"Không phân loại • Đơn {s.order_id} • bởi {config.name_of_user_id(uid) or 'n/a'}"
            import tempfile, aiohttp, os as _os
            tmp_path = None
            try:
                tmp_path = await bot.download_media(event.message.media, file=tempfile.gettempdir())
                if not tmp_path:
                    raise RuntimeError("download_media returned None")
                user_api_base = config.USER_API_BASE or "http://localhost:8090"
                async with aiohttp.ClientSession() as sess:
                    data = aiohttp.FormData()
                    data.add_field("chat_id", str(config.GROUP_CHAT_ID))
                    data.add_field("file", open(tmp_path, "rb"))
                    data.add_field("caption", caption)
                    data.add_field("reply_to", str(s.thread_id))
                    data.add_field("force_doc", "false")
                    async with sess.post(
                        f"{user_api_base}/api/tg/send-file",
                        data=data,
                        headers={"X-API-Key": config.USER_API_KEY or ""},
                    ) as resp:
                        if resp.status >= 400:
                            text = await resp.text()
                            raise RuntimeError(f"HTTP {resp.status}: {text}")
                        result = await resp.json()
                        if not result.get("ok"):
                            raise RuntimeError(result.get("error", "send-file failed"))
                await event.reply(f"Đã nhận media cho đơn {s.order_id}.")
            finally:
                if tmp_path and _os.path.exists(tmp_path):
                    try:
                        _os.unlink(tmp_path)
                    except OSError:
                        pass
        except Exception as e:
            log.warning("Failed to forward media to group via user account: %s", e)
            try:
                await bot.send_message(
                    config.GROUP_CHAT_ID,
                    caption,
                    file=event.message.media,
                    reply_to=s.thread_id,
                )
                await event.reply(f"Đã nhận media cho đơn {s.order_id}.")
            except Exception as e2:
                log.warning("Fallback bot send also failed: %s", e2)

        # Auto-complete soạn hàng
        if s.thread_id:
            try:
                await post_json(f"{ORDER_API_BASE}/api/order/soan", {"thread_id": s.thread_id, "user_id": uid})
                try:
                    fresh = db.get_order_by_thread(s.thread_id)
                    if fresh:
                        s.task_status = fresh.get("task_status")
                except Exception:
                    pass
                await send_help(bot, chat_id, s, caption="Đã tự động hoàn thành soạn hàng. Nếu đây không phải hình ảnh soạn hàng, hãy bấm 'Huỷ soạn'")
            except Exception as e:
                log.error("auto-soan error: %s", e)
        store.reset_timer(chat_id)
