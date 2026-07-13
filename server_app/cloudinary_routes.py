"""API chỉ-đọc cho thư viện ảnh Cloudinary.

API key/secret chỉ được đọc ở server. Frontend chỉ nhận URL phân phối ảnh công
khai và metadata cần để dựng gallery; không bao giờ nhận thông tin xác thực.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
from typing import Any

import aiohttp
from aiohttp import web

_FOLDER = os.getenv("CLOUDINARY_CAMERA_FOLDER", "camera_2026").strip("/")
_FIELDS = "asset_id,public_id,display_name,resource_type,type,format,width,height,bytes,created_at,secure_url"
_ACCOUNT_ID = re.compile(r"^[a-z0-9_-]{1,32}$")


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
    resource: dict[str, Any], account_id: str = "main", account_label: str = "MAIN"
) -> dict[str, Any] | None:
    """Giới hạn response và bỏ asset không phải ảnh upload công khai."""
    if resource.get("resource_type") != "image" or resource.get("type", "upload") != "upload":
        return None
    url = str(resource.get("secure_url") or "")
    if not url.startswith("https://"):
        return None
    public_id = str(resource.get("public_id") or "")
    return {
        "id": f"{account_id}:{resource.get('asset_id') or public_id}",
        "account_id": account_id,
        "account_label": account_label,
        "name": str(resource.get("display_name") or public_id.rsplit("/", 1)[-1]),
        "created_at": resource.get("created_at"),
        "width": int(resource.get("width") or 0),
        "height": int(resource.get("height") or 0),
        "bytes": int(resource.get("bytes") or 0),
        "thumbnail_url": _delivery_variant(url, "f_auto,q_auto:eco,c_fill,g_auto,w_640,h_640"),
        "preview_url": _delivery_variant(url, "f_auto,q_auto,c_limit,w_1800,h_1800"),
        "original_url": url,
    }


async def _get_cloudinary_page(account: dict[str, str], cursor: str | None) -> dict[str, Any]:
    base = f"https://api.cloudinary.com/v1_1/{account['cloud_name']}"
    params = {
        "asset_folder": account["folder"],
        "max_results": "48",
        "direction": "desc",
        "fields": _FIELDS,
    }
    if cursor:
        params["next_cursor"] = cursor

    timeout = aiohttp.ClientTimeout(total=15, connect=5)
    auth = aiohttp.BasicAuth(account["api_key"], account["api_secret"])
    async with aiohttp.ClientSession(timeout=timeout, auth=auth) as session:
        async with session.get(f"{base}/resources/by_asset_folder", params=params) as response:
            data = await response.json(content_type=None)
            # Tài khoản fixed-folder cũ có thể báo 400 hoặc trả rỗng dù public_id
            # vẫn nằm dưới "folder/...": tự chuyển sang truy vấn prefix.
            if response.status == 400 or (response.status < 400 and not data.get("resources") and not data.get("next_cursor")):
                fallback = {
                    "prefix": f"{account['folder']}/",
                    "max_results": "48",
                    "fields": _FIELDS,
                }
                if cursor:
                    fallback["next_cursor"] = cursor
                async with session.get(f"{base}/resources/image/upload", params=fallback) as legacy:
                    data = await legacy.json(content_type=None)
                    if legacy.status >= 400:
                        raise RuntimeError("Cloudinary không đọc được thư mục ảnh")
            elif response.status >= 400:
                raise RuntimeError("Cloudinary không đọc được thư mục ảnh")
    return data


async def camera_images_handler(request: web.Request) -> web.Response:
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
    state = _decode_cursor(cursor)
    if cursor and state is None:
        return web.json_response({"ok": False, "error": "cursor không hợp lệ"}, status=400)

    # Cursor None trong state nghĩa là account đó đã hết ảnh, không gọi lại trang đầu.
    active = [account for account in accounts if state is None or state.get(account["id"], "__new__") is not None]
    results = await asyncio.gather(
        *[_get_cloudinary_page(account, None if state is None else state.get(account["id"])) for account in active],
        return_exceptions=True,
    )
    images: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    next_state: dict[str, str | None] = {account["id"]: None for account in accounts}
    for account, result in zip(active, results):
        if isinstance(result, Exception):
            errors.append({"account_id": account["id"], "message": "Không đọc được nguồn ảnh"})
            continue
        next_state[account["id"]] = result.get("next_cursor")
        images.extend(
            image for raw in result.get("resources", [])
            if (image := _camera_image(raw, account["id"], account["label"]))
        )
    images.sort(key=lambda image: str(image.get("created_at") or ""), reverse=True)
    if not images and errors and len(errors) == len(active):
        return web.json_response({"ok": False, "error": "Không kết nối được Cloudinary", "sources": errors}, status=502)
    return web.json_response(
        {
            "ok": True,
            "folder": accounts[0]["folder"] if len({a["folder"] for a in accounts}) == 1 else None,
            "accounts": [{"id": account["id"], "label": account["label"], "folder": account["folder"]} for account in configured_accounts],
            "images": images,
            "next_cursor": _encode_cursor(next_state),
            "source_errors": errors,
        },
        headers={"Cache-Control": "private, no-store"},
    )
