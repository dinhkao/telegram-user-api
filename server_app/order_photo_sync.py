"""Đồng bộ ẢNH 2 chiều giữa webapp và topic Telegram của đơn.

- Web → Telegram: sau khi user upload ảnh ở webapp (image_routes), forward ảnh vào
  topic của đơn (ORDER_GROUP_ID, reply_to=thread_id) dưới dạng ảnh xem trước.
- Telegram → Web: nghe NewMessage trong ORDER_GROUP_ID; ảnh ai đó đăng trong topic
  → tải về, lưu vào order_images + đĩa (persist_order_image) → phát realtime để
  gallery webapp hiện ngay.

Chống lặp: ảnh do web forward ra mang msg.id được ghi vào _self_sent + cột
tg_message_id; handler inbound bỏ qua các id đó. Đăng ký: command_bootstrap.
Connects to: server_app/image_routes, order_images_store, chat_log.message_extract.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import tempfile

from telethon import events

from chat_log.message_extract import extract_thread_id, sender_name
from order_images_store import has_tg_message, set_tg_message_id
from server_app import state
from server_app.config import ORDER_GROUP_ID
from server_app.image_routes import persist_order_image

log = logging.getLogger("order_photo_sync")

_FULL_MAX = 1600
_THUMB_MAX = 400

# id các tin ảnh do chính process gửi ra (forward web → topic) — inbound bỏ qua.
_self_sent: set[int] = set()


def mark_self_sent(message_id: int) -> None:
    _self_sent.add(int(message_id))
    if len(_self_sent) > 5000:  # chặn phình vô hạn
        for mid in list(_self_sent)[:2500]:
            _self_sent.discard(mid)


def is_self_sent(message_id: int) -> bool:
    return int(message_id) in _self_sent


def _to_jpeg_tempfile(path: str) -> str:
    """Đọc file ảnh (webp/png/jpg) → JPEG tạm để Telegram hiện ảnh xem trước chắc chắn."""
    from PIL import Image, ImageOps

    im = Image.open(path)
    im = ImageOps.exif_transpose(im).convert("RGB")
    fd, tmp = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    im.save(tmp, "JPEG", quality=88)
    return tmp


async def forward_web_image_to_topic(thread_id: int, file_path: str, image_id: int, uploaded_by: str) -> None:
    """Gửi ảnh vừa upload ở web vào topic Telegram của đơn (chạy nền)."""
    client = state._tg_gateway or state._client
    if client is None:
        log.warning("forward ảnh: chưa có Telegram client")
        return
    try:
        jpeg = await asyncio.to_thread(_to_jpeg_tempfile, file_path)
    except Exception as e:  # noqa: BLE001
        log.warning("forward ảnh: convert JPEG lỗi: %s", e)
        return
    try:
        caption = f"🖼 Ảnh từ web · {uploaded_by}"
        msg = await client.send_file(ORDER_GROUP_ID, jpeg, reply_to=int(thread_id), caption=caption)
        mid = getattr(msg, "id", None)
        if mid:
            mark_self_sent(mid)
            await asyncio.to_thread(set_tg_message_id, image_id, int(mid))
            log.info("forward ảnh web→topic ok thread=%s msg=%s", thread_id, mid)
    except Exception as e:  # noqa: BLE001 — không làm hỏng upload nếu Telegram lỗi
        log.warning("forward ảnh web→topic lỗi thread=%s: %s", thread_id, e)
    finally:
        try:
            os.unlink(jpeg)
        except OSError:
            pass


def _process_incoming(photo_bytes: bytes) -> tuple[bytes, str, str, bytes, str, int, int]:
    """Ảnh tải từ Telegram → (full_bytes, '.jpg', 'image/jpeg', thumb_bytes, '.jpg', w, h)."""
    from PIL import Image, ImageOps

    im = Image.open(io.BytesIO(photo_bytes))
    im = ImageOps.exif_transpose(im).convert("RGB")

    full = im.copy()
    full.thumbnail((_FULL_MAX, _FULL_MAX))
    fb = io.BytesIO()
    full.save(fb, "JPEG", quality=82)

    thumb = im.copy()
    thumb.thumbnail((_THUMB_MAX, _THUMB_MAX))
    tb = io.BytesIO()
    thumb.save(tb, "JPEG", quality=72)

    return fb.getvalue(), ".jpg", "image/jpeg", tb.getvalue(), ".jpg", full.width, full.height


def register_inbound_photo_sync(client) -> None:
    """Nghe ảnh đăng trong topic đơn → nhập vào gallery webapp."""

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def _on_topic_photo(event):  # noqa: ANN001
        msg = event.message
        if not getattr(msg, "photo", None):
            return
        thread_id = extract_thread_id(msg)
        if not thread_id:
            return
        mid = int(msg.id)
        if is_self_sent(mid):
            return  # ảnh do web forward ra — đã có trong gallery
        # chờ chút cho forward web (nếu có) kịp gắn tg_message_id, rồi kiểm tra trùng
        await asyncio.sleep(2)
        if is_self_sent(mid):
            return
        try:
            if await asyncio.to_thread(has_tg_message, int(thread_id), mid):
                return
        except Exception as e:  # noqa: BLE001
            log.warning("check trùng ảnh lỗi: %s", e)

        try:
            data = await client.download_media(msg, file=bytes)
        except Exception as e:  # noqa: BLE001
            log.warning("tải ảnh Telegram lỗi thread=%s: %s", thread_id, e)
            return
        if not data:
            return
        try:
            full_b, full_ext, mime, thumb_b, thumb_ext, w, h = await asyncio.to_thread(_process_incoming, data)
        except Exception as e:  # noqa: BLE001
            log.warning("xử lý ảnh Telegram lỗi thread=%s: %s", thread_id, e)
            return

        who = sender_name(msg)
        if not who:
            try:
                s = await event.get_sender()
                who = getattr(s, "first_name", None) or getattr(s, "username", None) or "Telegram"
            except Exception:  # noqa: BLE001
                who = "Telegram"

        try:
            await persist_order_image(
                int(thread_id), full_b, mime, full_ext, thumb_b, thumb_ext,
                width=w, height=h, uploaded_by=who, tg_message_id=mid,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("lưu ảnh Telegram→web lỗi thread=%s: %s", thread_id, e)
            return
        from server_app.realtime import emit_order_changed
        emit_order_changed(int(thread_id))
        log.info("nhập ảnh topic→web ok thread=%s msg=%s by=%s", thread_id, mid, who)
