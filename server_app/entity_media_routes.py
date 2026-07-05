"""HTTP handlers bình luận + ảnh DÙNG CHUNG cho production slip / box…
Đường dẫn: /api/media/{scope}/{entity_id}/comments|images[...]. scope ∈ {production, box, report_bg}.
report_bg = ảnh nền "để dò" của trang sửa báo cáo phiếu SX (1 ảnh/phiếu, thay khi upload mới).

Web-only: KHÔNG sync Telegram, KHÔNG FCM/audit (khác order). Ảnh lưu xuống
ORDER_MEDIA_DIR/<scope>/<entity_id>/ (client đã resize/nén; thiếu thumb thì server tạo
bằng Pillow). Realtime: production phát production_changed; box thì bỏ qua.
Đăng ký ở server_app/app_factory.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid

from aiohttp import web

from entity_media_store import add_comment, add_image, delete_image, get_image, list_comments, list_images
from utils.paths import ORDER_MEDIA_DIR

log = logging.getLogger("entity_media_routes")

_ALLOWED_SCOPES = {"production", "box", "report_bg"}
_MAX_BYTES = 20 * 1024 * 1024
_EXT_BY_MIME = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_MIME_BY_EXT = {v: k for k, v in _EXT_BY_MIME.items()}


def _scope_entity(request: web.Request):
    """Trả (scope, entity_id) hợp lệ hoặc (None, None)."""
    scope = request.match_info.get("scope", "")
    if scope not in _ALLOWED_SCOPES:
        return None, None
    try:
        return scope, int(request.match_info.get("entity_id", ""))
    except (ValueError, TypeError):
        return scope, None


def _dir(scope: str, entity_id: int) -> str:
    d = os.path.join(ORDER_MEDIA_DIR, scope, str(entity_id))
    os.makedirs(d, exist_ok=True)
    return d


def _safe_path(scope: str, entity_id: int, name: str) -> str | None:
    base = os.path.normpath(os.path.join(ORDER_MEDIA_DIR, scope, str(entity_id)))
    full = os.path.normpath(os.path.join(base, name))
    if full != base and not full.startswith(base + os.sep):
        return None
    return full


def _ext_for(mime: str, filename: str) -> str:
    if mime in _EXT_BY_MIME:
        return _EXT_BY_MIME[mime]
    ext = os.path.splitext(filename or "")[1].lower()
    return ext if ext in _MIME_BY_EXT else ".jpg"


def _emit(scope: str, entity_id: int) -> None:
    try:
        if scope == "production":
            from server_app.realtime import emit_production_changed
            emit_production_changed(entity_id)
        elif scope == "box":
            from server_app.realtime import emit_box_changed
            emit_box_changed(entity_id)
    except Exception:  # noqa: BLE001
        pass


# ── Bình luận ────────────────────────────────────────────────────────────────
async def comments_list_handler(request: web.Request):
    scope, entity_id = _scope_entity(request)
    if entity_id is None:
        return web.json_response({"ok": False, "error": "scope/entity_id không hợp lệ"}, status=400)
    comments = await asyncio.to_thread(list_comments, scope, entity_id)
    return web.json_response({"ok": True, "comments": comments})


async def comments_add_handler(request: web.Request):
    scope, entity_id = _scope_entity(request)
    if entity_id is None:
        return web.json_response({"ok": False, "error": "scope/entity_id không hợp lệ"}, status=400)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return web.json_response({"ok": False, "error": "body phải là JSON"}, status=400)
    user = str(request.get("web_user") or body.get("user") or "?")
    try:
        comment = await asyncio.to_thread(add_comment, scope, entity_id, user, body.get("text", ""))
    except ValueError as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)
    _emit(scope, entity_id)
    return web.json_response({"ok": True, "comment": comment})


# ── Ảnh ──────────────────────────────────────────────────────────────────────
async def images_list_handler(request: web.Request):
    scope, entity_id = _scope_entity(request)
    if entity_id is None:
        return web.json_response({"ok": False, "error": "scope/entity_id không hợp lệ"}, status=400)
    images = await asyncio.to_thread(list_images, scope, entity_id)
    return web.json_response({"ok": True, "images": images})


def _make_thumb(photo_bytes: bytes, max_side: int = 400):
    import io

    from PIL import Image
    im = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
    im.thumbnail((max_side, max_side))
    out = io.BytesIO()
    im.save(out, format="JPEG", quality=72)
    return out.getvalue(), ".jpg"


async def images_upload_handler(request: web.Request):
    scope, entity_id = _scope_entity(request)
    if entity_id is None:
        return web.json_response({"ok": False, "error": "scope/entity_id không hợp lệ"}, status=400)
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
        except Exception as e:  # noqa: BLE001
            log.warning("thumb fallback lỗi: %s", e)
            thumb_bytes, thumb_ext = photo_bytes, ext

    def _to_int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    width, height = _to_int(data.get("width")), _to_int(data.get("height"))
    uploaded_by = str(request.get("web_user") or data.get("user") or "?")

    uid = uuid.uuid4().hex
    fname, tname = f"{uid}{ext}", f"{uid}_t{thumb_ext}"

    def _write():
        _dir(scope, entity_id)
        fp, tp = _safe_path(scope, entity_id, fname), _safe_path(scope, entity_id, tname)
        if not fp or not tp:
            raise ValueError("tên file không hợp lệ")
        with open(fp, "wb") as f:
            f.write(photo_bytes)
        with open(tp, "wb") as f:
            f.write(thumb_bytes)

    try:
        await asyncio.to_thread(_write)
        image = await asyncio.to_thread(
            add_image, scope, entity_id, fname, tname, photo_mime,
            size=len(photo_bytes), width=width, height=height, uploaded_by=uploaded_by,
        )
    except Exception as e:  # noqa: BLE001
        log.error("ghi file ảnh lỗi: %s", e)
        return web.json_response({"ok": False, "error": f"lưu file lỗi: {e}"}, status=500)

    _emit(scope, entity_id)
    return web.json_response({"ok": True, "image": image})


async def images_delete_handler(request: web.Request):
    scope, entity_id = _scope_entity(request)
    if entity_id is None:
        return web.json_response({"ok": False, "error": "scope/entity_id không hợp lệ"}, status=400)
    try:
        image_id = int(request.match_info.get("image_id", ""))
    except (ValueError, TypeError):
        return web.json_response({"ok": False, "error": "image_id không hợp lệ"}, status=400)

    row = await asyncio.to_thread(delete_image, image_id, scope, entity_id)
    if not row:
        return web.json_response({"ok": False, "error": "không tìm thấy ảnh"}, status=404)

    def _unlink():
        for name in (row.get("filename"), row.get("thumb")):
            if not name:
                continue
            p = _safe_path(scope, entity_id, name)
            if p and os.path.isfile(p):
                try:
                    os.unlink(p)
                except OSError as e:
                    log.warning("xoá file %s lỗi: %s", p, e)

    await asyncio.to_thread(_unlink)
    _emit(scope, entity_id)
    return web.json_response({"ok": True})


async def images_file_handler(request: web.Request):
    scope, entity_id = _scope_entity(request)
    if entity_id is None:
        return web.Response(status=400, text="scope/entity_id không hợp lệ")
    try:
        image_id = int(request.match_info.get("image_id", ""))
    except (ValueError, TypeError):
        return web.Response(status=400, text="image_id không hợp lệ")

    row = await asyncio.to_thread(get_image, image_id)
    if not row or row.get("scope") != scope or int(row["entity_id"]) != entity_id:
        return web.Response(status=404, text="không tìm thấy")
    name = row["thumb"] if request.query.get("size", "full") == "thumb" else row["filename"]
    path = _safe_path(scope, entity_id, name)
    if not path or not os.path.isfile(path):
        return web.Response(status=404, text="file không tồn tại")

    mime = _MIME_BY_EXT.get(os.path.splitext(name)[1].lower(), row.get("mime") or "image/jpeg")
    resp = web.FileResponse(path)
    resp.headers["Content-Type"] = mime
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp
