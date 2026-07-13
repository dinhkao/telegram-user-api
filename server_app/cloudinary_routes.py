"""API chỉ-đọc cho thư viện ảnh Cloudinary.

API key/secret chỉ được đọc ở server. Frontend chỉ nhận URL phân phối ảnh công
khai và metadata cần để dựng gallery; không bao giờ nhận thông tin xác thực.
"""
from __future__ import annotations

import asyncio
import base64
from contextlib import suppress
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import time
from typing import Any

import aiohttp
from aiohttp import web

from server_app import cloudinary_warm

_FOLDER = os.getenv("CLOUDINARY_CAMERA_FOLDER", "camera_2026").strip("/")
_CHANNELS = tuple(
    value.strip().strip("/")
    for value in os.getenv("CLOUDINARY_CAMERA_CHANNELS", "channel_11,channel_14").split(",")
    if value.strip()
)
_FIELDS = "asset_id,public_id,display_name,resource_type,type,format,width,height,bytes,created_at,secure_url"
_ACCOUNT_ID = re.compile(r"^[a-z0-9_-]{1,32}$")
_FIRST_PAGE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_FIRST_PAGE_CACHE_SECONDS = 60
_STALE_MAX_SECONDS = 600   # quá 10 phút → fetch đồng bộ, không trả bản quá cũ
_CACHE_REFRESH_SECONDS = 15
_IDLE_AFTER_SECONDS = 300  # không ai poll 5 phút → refresher nghỉ (đỡ quota Cloudinary)
_CACHE_TASK = web.AppKey("camera_cache_refresh_task", asyncio.Task)
# Dedup refresh nền theo cache key — nhiều request cùng key chia sẻ 1 fetch.
_INFLIGHT: dict[str, asyncio.Task] = {}
# Account dynamic-folder không hỗ trợ field `folder` (400) — nhớ sau lần đầu để khỏi
# tốn 1 round-trip retry MỖI call (nhân đôi quota Admin API).
_FOLDER_FIELD: dict[str, str] = {}
_last_poll = 0.0


def _accounts() -> list[dict[str, str]]:
    """Đọc nhiều account từ env, có fallback tương thích cấu hình đơn cũ.

    CLOUDINARY_ACCOUNTS=main,cam2
    CLOUDINARY_MAIN_CLOUD_NAME=... (tương tự API_KEY, API_SECRET, LABEL, FOLDER)
    """
    ids = [value.strip().lower() for value in os.getenv("CLOUDINARY_ACCOUNTS", "").split(",") if value.strip()]
    if not ids:
        ids = ["main"]
    result: list[dict[str, str]] = []
    for account_id in ids:
        if not _ACCOUNT_ID.fullmatch(account_id):
            continue
        prefix = f"CLOUDINARY_{account_id.upper().replace('-', '_')}"
        # Account main nhận cả tên biến cũ để nâng cấp không gián đoạn.
        legacy = account_id == "main"
        get = lambda suffix, default="": (
            os.getenv(f"{prefix}_{suffix}")
            or (os.getenv(f"CLOUDINARY_{suffix}") if legacy else None)
            or default
        ).strip()
        account = {
            "id": account_id,
            "label": get("LABEL", account_id.upper()),
            "cloud_name": get("CLOUD_NAME"),
            "api_key": get("API_KEY"),
            "api_secret": get("API_SECRET"),
            "folder": get("FOLDER", _FOLDER).strip("/"),
        }
        if account["cloud_name"] and account["api_key"] and account["api_secret"]:
            result.append(account)
    return result


def _decode_cursor(value: str) -> dict[str, str | None] | None:
    if not value:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if not isinstance(data, dict):
            return None
        return {str(k): (str(v) if v is not None else None) for k, v in data.items()}
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _encode_cursor(state: dict[str, str | None]) -> str | None:
    if not any(value for value in state.values()):
        return None
    raw = json.dumps(state, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _delivery_variant(url: str, transformation: str) -> str:
    """Chèn transformation vào URL ảnh upload chuẩn của Cloudinary."""
    marker = "/image/upload/"
    if not url.startswith("https://") or marker not in url:
        return url
    return url.replace(marker, f"{marker}{transformation}/", 1)


def _camera_image(
    resource: dict[str, Any], account_id: str = "main", account_label: str = "MAIN",
    root_folder: str = _FOLDER,
) -> dict[str, Any] | None:
    """Giới hạn response và bỏ asset không phải ảnh upload công khai."""
    if resource.get("resource_type") != "image" or resource.get("type", "upload") != "upload":
        return None
    url = str(resource.get("secure_url") or "")
    if not url.startswith("https://"):
        return None
    public_id = str(resource.get("public_id") or "")
    resource_folder = str(resource.get("asset_folder") or resource.get("folder") or public_id.rsplit("/", 1)[0])
    channel = resource_folder.removeprefix(f"{root_folder}/").split("/", 1)[0]
    return {
        "id": f"{account_id}:{resource.get('asset_id') or public_id}",
        "account_id": account_id,
        "account_label": account_label,
        "channel": channel if channel in _CHANNELS else "",
        "name": str(resource.get("display_name") or public_id.rsplit("/", 1)[-1]),
        "created_at": resource.get("created_at"),
        "width": int(resource.get("width") or 0),
        "height": int(resource.get("height") or 0),
        "bytes": int(resource.get("bytes") or 0),
        # Ô lưới tối đa ~160 CSS px: 320px đủ nét cả màn Retina 2x. Không crop
        # AI g_auto (CSS object-fit đã crop) → derived asset tạo nhanh và nhẹ hơn.
        "thumbnail_url": _delivery_variant(url, "f_auto,q_auto:low,c_limit,w_320"),
        # 1280px đủ cho viewport app 640px ở DPR 2; nhẹ hơn khoảng một nửa bản
        # 1800px. Viewer hiện thumbnail ngay trong lúc bản nét được tạo/tải.
        "preview_url": _delivery_variant(url, "f_auto,q_auto:eco,c_limit,w_1280,h_1280"),
        "original_url": url,
    }


def _normalize_iso_time(value: str) -> str | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _search_expression(
    account: dict[str, str], channel: str | None, folder_field: str,
    created_from: str | None = None, created_to: str | None = None,
) -> str:
    folders = [f"{account['folder']}/{channel}"] if channel else [f"{account['folder']}/{name}" for name in _CHANNELS]
    folder_query = " OR ".join(f"{folder_field}={json.dumps(folder)}" for folder in folders)
    parts = ["resource_type:image", "type:upload", f"({folder_query})"]
    if created_from:
        parts.append(f"created_at>={json.dumps(created_from)}")
    if created_to:
        parts.append(f"created_at<={json.dumps(created_to)}")
    return " AND ".join(parts)


async def _fetch_page(
    account: dict[str, str], cursor: str | None, channel: str | None = None,
    created_from: str | None = None, created_to: str | None = None,
) -> dict[str, Any]:
    """Gọi Cloudinary Search API thuần (không cache) qua session dùng chung."""
    base = f"https://api.cloudinary.com/v1_1/{account['cloud_name']}"
    auth = aiohttp.BasicAuth(account["api_key"], account["api_secret"])
    field = _FOLDER_FIELD.get(account["id"], "folder")
    body: dict[str, Any] = {
        "expression": _search_expression(account, channel, field, created_from, created_to),
        "sort_by": [{"created_at": "desc"}],
        "max_results": 100,
        "fields": _FIELDS.split(","),
    }
    if cursor:
        body["next_cursor"] = cursor

    session = await cloudinary_warm.get_session()
    async with session.post(f"{base}/resources/search", json=body, auth=auth) as response:
        data = await response.json(content_type=None)
        # Dynamic-folder không hỗ trợ field `folder`; thử lại bằng asset_folder.
        if response.status == 400 and field == "folder":
            body["expression"] = _search_expression(account, channel, "asset_folder", created_from, created_to)
            async with session.post(f"{base}/resources/search", json=body, auth=auth) as dynamic:
                data = await dynamic.json(content_type=None)
                if dynamic.status >= 400:
                    raise RuntimeError("Cloudinary không đọc được thư mục ảnh")
                _FOLDER_FIELD[account["id"]] = "asset_folder"  # memo khi chắc chắn đúng
        elif response.status >= 400:
            raise RuntimeError("Cloudinary không đọc được thư mục ảnh")
    return data


def _spawn_refresh(key: str, account: dict[str, str], channel: str | None) -> asyncio.Task:
    """Refresh trang đầu cho 1 cache key, dedup: request trùng chờ chung 1 task."""
    task = _INFLIGHT.get(key)
    if task is not None and not task.done():
        return task

    async def _run() -> dict[str, Any]:
        try:
            data = await _fetch_page(account, None, channel)
            _FIRST_PAGE_CACHE[key] = (time.monotonic(), data)
            return data
        finally:
            _INFLIGHT.pop(key, None)

    task = asyncio.create_task(_run(), name=f"cloudinary.refresh.{key}")
    # Spawn nền không ai await → tiêu thụ exception, khỏi "never retrieved" log.
    task.add_done_callback(lambda t: None if t.cancelled() else t.exception())
    _INFLIGHT[key] = task
    return task


async def _get_cloudinary_page(
    account: dict[str, str], cursor: str | None, channel: str | None = None,
    created_from: str | None = None, created_to: str | None = None, *, force: bool = False
) -> dict[str, Any]:
    """Trang đầu qua cache stale-while-revalidate; trang sau/lọc thời gian gọi thẳng."""
    use_cache = cursor is None and not created_from and not created_to
    if not use_cache:
        return await _fetch_page(account, cursor, channel, created_from, created_to)
    key = f"{account['id']}:{channel or '*'}"
    if force:
        return await _spawn_refresh(key, account, channel)
    entry = _FIRST_PAGE_CACHE.get(key)
    age = None if entry is None else time.monotonic() - entry[0]
    if entry is not None and age < _FIRST_PAGE_CACHE_SECONDS:
        return entry[1]
    if entry is not None and age < _STALE_MAX_SECONDS:
        _spawn_refresh(key, account, channel)  # trả bản cũ NGAY, làm mới chạy nền
        return entry[1]
    return await _spawn_refresh(key, account, channel)  # nguội/quá cũ → chờ fetch (vẫn dedup)


async def camera_images_handler(request: web.Request) -> web.Response:
    global _last_poll
    _last_poll = time.monotonic()  # refresher chỉ chạy khi gallery đang được xem
    cursor = (request.query.get("cursor") or "").strip()
    if len(cursor) > 1024:
        return web.json_response({"ok": False, "error": "cursor không hợp lệ"}, status=400)
    configured_accounts = _accounts()
    if not configured_accounts:
        return web.json_response({"ok": False, "error": "Cloudinary chưa được cấu hình trên server"}, status=503)
    accounts = configured_accounts
    requested = (request.query.get("account") or "").strip().lower()
    if requested:
        accounts = [account for account in accounts if account["id"] == requested]
        if not accounts:
            return web.json_response({"ok": False, "error": "Nguồn ảnh không tồn tại"}, status=404)
    channel = (request.query.get("channel") or "").strip().lower()
    if channel and channel not in _CHANNELS:
        return web.json_response({"ok": False, "error": "Kênh camera không tồn tại"}, status=404)
    try:
        created_from = _normalize_iso_time((request.query.get("from") or "").strip())
        created_to = _normalize_iso_time((request.query.get("to") or "").strip())
    except ValueError:
        return web.json_response({"ok": False, "error": "Khoảng thời gian không hợp lệ"}, status=400)
    if created_from and created_to and created_from > created_to:
        return web.json_response({"ok": False, "error": "Thời gian bắt đầu phải trước thời gian kết thúc"}, status=400)
    state = _decode_cursor(cursor)
    if cursor and state is None:
        return web.json_response({"ok": False, "error": "cursor không hợp lệ"}, status=400)

    # Cursor None trong state nghĩa là account đó đã hết ảnh, không gọi lại trang đầu.
    active = [account for account in accounts if state is None or state.get(account["id"], "__new__") is not None]
    results = await asyncio.gather(
        *[_get_cloudinary_page(
            account, None if state is None else state.get(account["id"]), channel or None,
            created_from, created_to,
        ) for account in active],
        return_exceptions=True,
    )
    images: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    total_count = 0
    next_state: dict[str, str | None] = {account["id"]: None for account in accounts}
    for account, result in zip(active, results):
        if isinstance(result, Exception):
            errors.append({"account_id": account["id"], "message": "Không đọc được nguồn ảnh"})
            continue
        next_state[account["id"]] = result.get("next_cursor")
        total_count += int(result.get("total_count") or 0)
        images.extend(
            image for raw in result.get("resources", [])
            if (image := _camera_image(raw, account["id"], account["label"], account["folder"]))
        )
    images.sort(key=lambda image: str(image.get("created_at") or ""), reverse=True)
    if not images and errors and len(errors) == len(active):
        return web.json_response({"ok": False, "error": "Không kết nối được Cloudinary", "sources": errors}, status=502)
    body = json.dumps(
        {
            "ok": True,
            "folder": accounts[0]["folder"] if len({a["folder"] for a in accounts}) == 1 else None,
            "accounts": [{"id": account["id"], "label": account["label"], "folder": account["folder"]} for account in configured_accounts],
            "channels": [
                {"id": name, "label": name.replace("_", " ").title(), "folder": f"{accounts[0]['folder']}/{name}"}
                for name in _CHANNELS
            ],
            "images": images,
            "total_count": total_count,
            "next_cursor": _encode_cursor(next_state),
            "source_errors": errors,
            "range": {"from": created_from, "to": created_to},
        },
        ensure_ascii=False, separators=(",", ":"),
    )
    # ETag + no-cache (thay no-store): poll 10s không có ảnh mới → browser tự gửi
    # If-None-Match, nhận 304 rỗng thay vì tải lại 40-80KB metadata.
    etag = f'"{hashlib.md5(body.encode("utf-8")).hexdigest()}"'
    headers = {"Cache-Control": "private, no-cache", "ETag": etag}
    if request.headers.get("If-None-Match") == etag:
        return web.Response(status=304, headers=headers)
    return web.Response(text=body, content_type="application/json", headers=headers)


def _cached_images(accounts: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Ảnh (đã chuẩn hoá, sort mới→cũ) từ cache trang đầu all-channels của mỗi account."""
    images: list[dict[str, Any]] = []
    for account in accounts:
        entry = _FIRST_PAGE_CACHE.get(f"{account['id']}:*")
        if not entry:
            continue
        images.extend(
            image for raw in entry[1].get("resources", [])
            if (image := _camera_image(raw, account["id"], account["label"], account["folder"]))
        )
    images.sort(key=lambda image: str(image.get("created_at") or ""), reverse=True)
    return images


async def warm_camera_cache(_app: web.Application) -> None:
    """Làm nóng trang mới nhất trong RAM khi server start; không ghi ổ đĩa."""
    accounts = _accounts()
    if not accounts:
        return
    await asyncio.gather(
        *[_get_cloudinary_page(account, None, force=True) for account in accounts],
        return_exceptions=True,
    )
    # Ảnh cũ coi như đã có derived asset (từ lần xem trước) — chỉ ảnh MỚI sau boot
    # mới được warm, tránh burst hàng trăm request mỗi lần restart.
    cloudinary_warm.seed_warmed(image["id"] for image in _cached_images(accounts))
    _app[_CACHE_TASK] = asyncio.create_task(_refresh_camera_cache(), name="cloudinary.camera-cache")


async def _refresh_camera_cache() -> None:
    while True:
        await asyncio.sleep(_CACHE_REFRESH_SECONDS)
        if time.monotonic() - _last_poll > _IDLE_AFTER_SECONDS:
            continue  # không ai mở gallery → nghỉ, không tốn quota Cloudinary
        accounts = _accounts()
        await asyncio.gather(
            *[_get_cloudinary_page(account, None, force=True) for account in accounts],
            return_exceptions=True,
        )
        # Warm derived asset (thumb + preview) của ảnh mới trên CDN trước khi user xem.
        await cloudinary_warm.warm_urls(cloudinary_warm.collect_warm_urls(_cached_images(accounts)))


async def stop_camera_cache(app: web.Application) -> None:
    task = app.get(_CACHE_TASK)
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    for inflight in list(_INFLIGHT.values()):
        inflight.cancel()
        with suppress(BaseException):
            await inflight
    await cloudinary_warm.close_session()
