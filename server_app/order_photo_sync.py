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
from collections import deque

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
# set để tra O(1) + deque giữ thứ tự để evict FIFO (không evict nhầm id còn trong cửa sổ dedup).
_self_sent: set[int] = set()
_self_sent_q: deque[int] = deque()
_SELF_SENT_MAX = 5000


def mark_self_sent(message_id: int) -> None:
    mid = int(message_id)
    if mid in _self_sent:
        return
    _self_sent.add(mid)
    _self_sent_q.append(mid)
    while len(_self_sent_q) > _SELF_SENT_MAX:  # evict id CŨ NHẤT
        _self_sent.discard(_self_sent_q.popleft())


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


async def import_sent_image(thread_id, file_bytes: bytes, tg_message_id, uploaded_by: str = "Telegram"):
    """Nhập vào gallery 1 ảnh VỪA GỬI vào topic đơn qua /api/tg/send-file (vd bot
    forward ảnh từ session). Cần gọi TRỰC TIẾP vì Telethon KHÔNG bắn NewMessage cho
    tin do chính client gửi bằng send_file → handler inbound không thấy. Chống trùng
    bằng tg_message_id. Phát realtime + FCM + ghi lịch sử như mọi lần thêm ảnh."""
    if not thread_id or not file_bytes:
        return None
    try:
        if await asyncio.to_thread(has_tg_message, int(thread_id), int(tg_message_id)):
            return None
    except Exception:  # noqa: BLE001
        pass
    full_b, full_ext, mime, thumb_b, thumb_ext, w, h = await asyncio.to_thread(_process_incoming, file_bytes)
    img = await persist_order_image(
        int(thread_id), full_b, mime, full_ext, thumb_b, thumb_ext,
        width=w, height=h, uploaded_by=uploaded_by or "Telegram", tg_message_id=int(tg_message_id),
    )
    mark_self_sent(int(tg_message_id))  # phòng NewMessage có bắn thì cũng bỏ qua
    from server_app.realtime import emit_order_changed
    emit_order_changed(int(thread_id))
    from server_app.notify import push_bg  # ghi notification center + FCM từ 1 chỗ
    push_bg("🖼 Ảnh mới", f"{uploaded_by} thêm ảnh vào đơn", {"thread_id": str(thread_id), "type": "image", "image_id": str(img["id"])})
    from audit_log import async_log_event
    await async_log_event("order.image_added", actor_type="telegram", actor_id=uploaded_by,
                          thread_id=int(thread_id), payload={"image_id": img["id"]})
    log.info("nhập ảnh send-file→web ok thread=%s msg=%s by=%s", thread_id, tg_message_id, uploaded_by)
    return img


def register_inbound_photo_sync(client) -> None:
    """Nghe ảnh đăng trong topic đơn → nhập vào gallery webapp."""

    @client.on(events.NewMessage(chats=ORDER_GROUP_ID))
    async def _on_topic_photo(event):  # noqa: ANN001
        msg = event.message
        media = getattr(msg, "media", None)
        if media is None:
            return
        is_photo = bool(getattr(msg, "photo", None))
        doc = getattr(msg, "document", None)
        is_image_doc = bool(doc and (getattr(doc, "mime_type", "") or "").startswith("image/"))
        log.info("[inbound] media msg id=%s photo=%s image_doc=%s type=%s out=%s",
                 msg.id, is_photo, is_image_doc, type(media).__name__, getattr(event, "out", None))
        if not (is_photo or is_image_doc):
            return
        thread_id = extract_thread_id(msg)
        log.info("[inbound] msg=%s thread_id=%s", msg.id, thread_id)
        if not thread_id:
            return
        mid = int(msg.id)
        if is_self_sent(mid):
            log.info("[inbound] skip self-sent msg=%s", mid)
            return  # ảnh do web forward ra — đã có trong gallery
        # chờ chút cho forward web (nếu có) kịp gắn tg_message_id, rồi kiểm tra trùng
        await asyncio.sleep(2)
        if is_self_sent(mid):
            return
        try:
            if await asyncio.to_thread(has_tg_message, int(thread_id), mid):
                log.info("[inbound] skip dup tg_message=%s", mid)
                return
        except Exception as e:  # noqa: BLE001
            log.warning("check trùng ảnh lỗi: %s", e)

        log.info("[inbound] downloading msg=%s thread=%s", mid, thread_id)
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
            saved = await persist_order_image(
                int(thread_id), full_b, mime, full_ext, thumb_b, thumb_ext,
                width=w, height=h, uploaded_by=who, tg_message_id=mid,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("lưu ảnh Telegram→web lỗi thread=%s: %s", thread_id, e)
            return
        from server_app.realtime import emit_order_changed
        emit_order_changed(int(thread_id))
        from server_app.notify import push_bg  # ghi notification center + FCM từ 1 chỗ
        push_bg("🖼 Ảnh mới", f"{who} (Telegram) thêm ảnh vào đơn", {"thread_id": str(thread_id), "type": "image", "image_id": str(saved["id"])})
        # Ghi vào lịch sử thao tác (kèm id ảnh để hiện thumbnail)
        from audit_log import async_log_event
        await async_log_event("order.image_added", actor_type="telegram", actor_id=who,
                              thread_id=int(thread_id), payload={"image_id": saved["id"]})
        log.info("nhập ảnh topic→web ok thread=%s msg=%s by=%s", thread_id, mid, who)
