"""bot_handlers/media_events.py — NewMessage handler for media."""
import logging
import tempfile
import aiohttp
import os as _os
from telethon import events
from bot_core import config, db, store
from bot_core.utils import mark_task
import bot_flows as flows
from .session import send_help

log = logging.getLogger("bot.handlers")

def register_media_handlers(bot):
    @bot.on(events.NewMessage)
    async def on_media(event):
        if not event.message.media:
            return
        chat_id, uid = event.chat_id, event.sender_id
        if not config.is_allowed(uid):
            return
        s = store.get(chat_id)
        if not s or not s.order_id:
            return
        if s.nop_wizard and s.nop_wizard.get("active") and s.nop_wizard.get("step") == "wait_photo":
            handled = await flows.handle_nop_wizard_photo(bot, event, s)
            if handled:
                return
        try:
            caption = f"Không phân loại • Đơn {s.order_id} • bởi {config.name_of_user_id(uid) or 'n/a'}"
            tmp_path = None
            try:
                tmp_path = await bot.download_media(event.message.media, file=tempfile.gettempdir())
                if not tmp_path:
                    raise RuntimeError("download_media returned None")
                async with aiohttp.ClientSession() as sess:
                    data = aiohttp.FormData()
                    data.add_field("chat_id", str(config.GROUP_CHAT_ID))
                    data.add_field("file", open(tmp_path, "rb"))
                    data.add_field("caption", caption)
                    data.add_field("reply_to", str(s.thread_id))
                    data.add_field("force_doc", "false")
                    async with sess.post(
                        f"{config.USER_API_BASE}/api/tg/send-file",
                        data=data, headers={"X-API-Key": config.USER_API_KEY or ""}) as resp:
                        if resp.status >= 400:
                            raise RuntimeError(f"HTTP {resp.status}: {await resp.text()}")
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
            log.warning("Failed to forward media: %s", e)
            try:
                await bot.send_message(config.GROUP_CHAT_ID, caption,
                    file=event.message.media, reply_to=s.thread_id)
                await event.reply(f"Đã nhận media cho đơn {s.order_id}.")
            except Exception as e2:
                log.warning("Fallback send also failed: %s", e2)
        if s.thread_id:
            ok = await mark_task(s, "soan", uid)
            if ok:
                await send_help(bot, chat_id, s,
                    caption="Đã tự động hoàn thành soạn hàng. Nếu đây không phải hình ảnh soạn hàng, hãy bấm 'Huỷ soạn'")
        store.reset_timer(chat_id)
