"""bot_don_hang/media.py — Media handling (forward to group)."""
import logging

from telethon import Button

from bot_core import config, store
from bot_core.utils import post_json
import bot_core.db as db
from bot_handlers import send_help

log = logging.getLogger("bot.media")

_HANDLED_PHOTOS: set[int] = set()


async def handle_photo(bot, event):
    """Handle photo sent during active session."""
    chat_id = event.chat_id
    uid = event.sender_id
    if not config.is_allowed(uid):
        return
    s = store.get(chat_id)
    if not s:
        return

    msg_id = event.id
    if msg_id in _HANDLED_PHOTOS:
        return
    _HANDLED_PHOTOS.add(msg_id)

    store.reset_timer(chat_id)

    # Extract largest photo
    photo = event.message.photo
    if not photo:
        return

    # Build inline keyboard for media chooser
    kb = [
        [Button.inline("Soạn hàng", f"pt:soan:{msg_id}:{s.order_id}".encode())],
        [Button.inline("Giao hàng", f"pt:giao:{msg_id}:{s.order_id}".encode())],
        [Button.inline("Nộp tiền", f"pt:nop:{msg_id}:{s.order_id}".encode())],
        [Button.inline("Nhận tiền", f"pt:nhan:{msg_id}:{s.order_id}".encode())],
    ]
    await event.reply("Chọn loại media này:", buttons=kb)

    # Cache photo file_id
    s.pending_media[msg_id] = {"file_id": photo.id, "kind": "photo"}


async def handle_callback_media(bot, event):
    """Handle inline button for media type (soan/giao/nop/nhan)."""
    data = event.data.decode() if event.data else ""
    if not data.startswith("pt:"):
        return
    parts = data.split(":")
    if len(parts) < 4:
        return
    short = parts[1]
    original_mid = int(parts[2])
    order_id_from_cb = parts[3] if len(parts) > 3 else ""

    chat_id = event.chat_id
    s = store.get(chat_id)
    if not s or not s.order_id:
        await event.answer("Không có phiên đơn hàng.")
        return

    order_id = s.order_id or order_id_from_cb
    media = s.pending_media.get(original_mid)
    if not media:
        await event.answer("Không tìm thấy media.")
        return

    label_map = {"soan": "Soạn hàng", "giao": "Giao hàng", "nop": "Nộp tiền", "nhan": "Nhận tiền"}
    label = label_map.get(short, short)

    # Forward to group
    if s.thread_id:
        try:
            entity = await bot.get_entity(config.GROUP_CHAT_ID)
            await bot.send_file(
                entity,
                media["file_id"],
                reply_to=s.thread_id,
                caption=f"{label} • Đơn {order_id} • bởi {config.name_of_user_id(event.sender_id) or 'n/a'}",
            )
        except Exception as e:
            log.error("Forward media error: %s", e)

    # Auto complete soan
    if short == "soan" and s.thread_id:
        try:
            await post_json(
                f"{config.ORDER_API_BASE}/api/order/soan",
                {"thread_id": s.thread_id, "user_id": event.sender_id},
            )
            order = db.get_order(order_id)
            if order:
                s.task_status = order.get("task_status")
        except Exception as e:
            log.error("auto-soan error: %s", e)

    await event.answer(f"Đã thêm media vào {label}.")
    await event.edit("Đã xác nhận.")
    store.reset_timer(chat_id)

    # Remove chooser message
    try:
        await event.delete()
    except Exception as e:
        log.debug("could not delete chooser message: %s", e)
