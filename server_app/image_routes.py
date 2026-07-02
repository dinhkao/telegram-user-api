"""HTTP handlers ảnh đính kèm đơn — /api/order/{thread_id}/images[/{id}[/file]].

GET   list  → metadata ảnh (client tự dựng URL kèm token).
POST  upload→ multipart 'photo' (bắt buộc, đã resize/nén phía client) + 'thumb'
              (tùy chọn; thiếu thì server tự tạo bằng Pillow). Lưu file xuống
              utils.paths.ORDER_MEDIA_DIR/<thread_id>/, metadata vào order_images.
DELETE      → xoá dòng + file.
GET .../file?size=thumb|full → trả file (Cache-Control immutable, có chặn traversal).

Auth: web_auth middleware tự chặn (route dưới /api/). Người tải = request['web_user'].
Mỗi lần thêm/xoá phát realtime emit_order_changed. Đăng ký ở server_app/app_factory.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid

from aiohttp import web

from order_images_store import add_image, delete_image, get_image, list_images
from utils.paths import ORDER_MEDIA_DIR

log = logging.getLogger("image_routes")

_MAX_BYTES = 20 * 1024 * 1024  # 20MB/ảnh (ảnh đã nén phía client thường < 300KB)
_EXT_BY_MIME = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_MIME_BY_EXT = {v: k for k, v in _EXT_BY_MIME.items()}


def _thread_id(request: web.Request) -> int | None:
    try:
        return int(request.match_info.get("thread_id", ""))
    except (ValueError, TypeError):
        return None


def _thread_dir(thread_id: int) -> str:
    d = os.path.join(ORDER_MEDIA_DIR, str(thread_id))
    os.makedirs(d, exist_ok=True)
    return d


def _safe_path(thread_id: int, name: str) -> str | None:
    """Ghép ORDER_MEDIA_DIR/<thread_id>/<name> và chặn path-traversal."""
    base = os.path.normpath(_thread_dir(thread_id))
    full = os.path.normpath(os.path.join(base, name))
    if full != base and not full.startswith(base + os.sep):
        return None
    return full


def _ext_for(mime: str, filename: str) -> str:
    if mime in _EXT_BY_MIME:
        return _EXT_BY_MIME[mime]
    ext = os.path.splitext(filename or "")[1].lower()
    return ext if ext in _MIME_BY_EXT else ".jpg"


async def persist_order_image(
    thread_id: int,
    full_bytes: bytes,
    mime: str,
    ext: str,
    thumb_bytes: bytes,
    thumb_ext: str,
    *,
    width: int = 0,
    height: int = 0,
    uploaded_by: str = "?",
    tg_message_id: int | None = None,
) -> dict:
    """Ghi file (full + thumb) xuống ORDER_MEDIA_DIR/<thread_id>/ + 1 dòng metadata.

    Dùng chung cho upload web (image_routes) và nhập từ Telegram (order_photo_sync).
    Không phát realtime — caller tự gọi emit_order_changed.
    """
    uid = uuid.uuid4().hex
    fname, tname = f"{uid}{ext}", f"{uid}_t{thumb_ext}"

    def _write():
        fp = _safe_path(thread_id, fname)
        tp = _safe_path(thread_id, tname)
        if not fp or not tp:
            raise ValueError("tên file không hợp lệ")
        with open(fp, "wb") as f:
            f.write(full_bytes)
        with open(tp, "wb") as f:
            f.write(thumb_bytes)

    await asyncio.to_thread(_write)
    return await asyncio.to_thread(
        add_image, thread_id, fname, tname, mime,
        size=len(full_bytes), width=width, height=height,
        uploaded_by=uploaded_by, tg_message_id=tg_message_id,
    )


async def images_list_handler(request: web.Request):
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    images = await asyncio.to_thread(list_images, thread_id)
    return web.json_response({"ok": True, "images": images})


def _make_thumb(photo_bytes: bytes, max_side: int = 400) -> tuple[bytes, str]:
    """Fallback tạo thumbnail server-side bằng Pillow khi client không gửi 'thumb'."""
    import io

    from PIL import Image

    im = Image.open(io.BytesIO(photo_bytes))
    im = im.convert("RGB")
    im.thumbnail((max_side, max_side))
    out = io.BytesIO()
    im.save(out, format="JPEG", quality=72)
    return out.getvalue(), ".jpg"


async def images_upload_handler(request: web.Request):
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        data = await request.post()
    except Exception as e:  # noqa: BLE001
        return web.json_response({"ok": False, "error": f"multipart lỗi: {e}"}, status=400)

    photo = data.get("photo")
    if not photo or not hasattr(photo, "file"):
        return web.json_response({"ok": False, "error": "thiếu file 'photo'"}, status=400)
    photo_bytes = photo.file.read()
    if not photo_bytes:
        return web.json_response({"ok": False, "error": "file rỗng"}, status=400)
    if len(photo_bytes) > _MAX_BYTES:
        return web.json_response({"ok": False, "error": "ảnh quá lớn (>20MB)"}, status=413)

    photo_mime = (getattr(photo, "content_type", "") or "").lower()
    if photo_mime not in _EXT_BY_MIME:
        photo_mime = _MIME_BY_EXT.get(_ext_for(photo_mime, getattr(photo, "filename", "")), "image/jpeg")
    ext = _ext_for(photo_mime, getattr(photo, "filename", ""))

    thumb_field = data.get("thumb")
    if thumb_field is not None and hasattr(thumb_field, "file"):
        thumb_bytes = thumb_field.file.read()
        thumb_mime = (getattr(thumb_field, "content_type", "") or "image/jpeg").lower()
        thumb_ext = _ext_for(thumb_mime, getattr(thumb_field, "filename", ""))
    else:
        try:
            thumb_bytes, thumb_ext = await asyncio.to_thread(_make_thumb, photo_bytes)
            thumb_mime = "image/jpeg"
        except Exception as e:  # noqa: BLE001 — thiếu thumb thì dùng luôn ảnh gốc
            log.warning("thumb fallback lỗi: %s", e)
            thumb_bytes, thumb_ext, thumb_mime = photo_bytes, ext, photo_mime

    def _to_int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    width, height = _to_int(data.get("width")), _to_int(data.get("height"))
    uploaded_by = str(request.get("web_user") or data.get("user") or "?")

    try:
        image = await persist_order_image(
            thread_id, photo_bytes, photo_mime, ext, thumb_bytes, thumb_ext,
            width=width, height=height, uploaded_by=uploaded_by,
        )
    except Exception as e:  # noqa: BLE001
        log.error("ghi file ảnh lỗi: %s", e)
        return web.json_response({"ok": False, "error": f"lưu file lỗi: {e}"}, status=500)

    from server_app.realtime import emit_order_changed
    emit_order_changed(thread_id)
    # Forward ảnh vào topic Telegram của đơn (nền, không chặn/không làm hỏng upload)
    from server_app.order_photo_sync import forward_web_image_to_topic
    from server_app.tasks import spawn_tracked
    fp = _safe_path(thread_id, image["filename"])
    if fp:
        spawn_tracked(
            "order_photo.forward",
            forward_web_image_to_topic(thread_id, fp, image["id"], uploaded_by),
            context={"thread_id": thread_id, "image_id": image["id"]},
        )
    return web.json_response({"ok": True, "image": image})


async def images_delete_handler(request: web.Request):
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.json_response({"ok": False, "error": "thread_id không hợp lệ"}, status=400)
    try:
        image_id = int(request.match_info.get("image_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "image_id không hợp lệ"}, status=400)

    row = await asyncio.to_thread(delete_image, image_id, thread_id)
    if not row:
        return web.json_response({"ok": False, "error": "không tìm thấy ảnh"}, status=404)

    def _unlink():
        for name in (row.get("filename"), row.get("thumb")):
            if not name:
                continue
            p = _safe_path(thread_id, name)
            if p and os.path.isfile(p):
                try:
                    os.unlink(p)
                except OSError as e:
                    log.warning("xoá file %s lỗi: %s", p, e)

    await asyncio.to_thread(_unlink)
    from server_app.realtime import emit_order_changed
    emit_order_changed(thread_id)
    return web.json_response({"ok": True})


async def images_file_handler(request: web.Request):
    thread_id = _thread_id(request)
    if thread_id is None:
        return web.Response(status=400, text="thread_id không hợp lệ")
    try:
        image_id = int(request.match_info.get("image_id", ""))
    except (ValueError, TypeError):
        return web.Response(status=400, text="image_id không hợp lệ")

    row = await asyncio.to_thread(get_image, image_id)
    if not row or int(row["thread_id"]) != thread_id:
        return web.Response(status=404, text="không tìm thấy")
    want_thumb = request.query.get("size", "full") == "thumb"
    name = row["thumb"] if want_thumb else row["filename"]
    path = _safe_path(thread_id, name)
    if not path or not os.path.isfile(path):
        return web.Response(status=404, text="file không tồn tại")

    mime = _MIME_BY_EXT.get(os.path.splitext(name)[1].lower(), row.get("mime") or "image/jpeg")
    resp = web.FileResponse(path)
    resp.headers["Content-Type"] = mime
    # file đặt tên theo uuid nội dung → bất biến, cache mạnh
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp
