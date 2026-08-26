"""Tra cứu thông tin người nộp thuế theo MST — GET /api/mst-lookup?mst=.

Trang tra cứu chính thức của GDT (tracuunnt.gdt.gov.vn) có CAPTCHA, không có
API → dùng API công khai VietQR (api.vietqr.io/v2/business/{mst}, dữ liệu tổng
hợp từ chính gdt.gov.vn, trễ ~15 ngày). Nhận cả MST 10 số lẫn SỐ ĐỊNH DANH CÁ
NHÂN 12 số (hộ kinh doanh). Dùng cho form HĐ điện tử VNPT: gõ MST → tự điền tên
đơn vị + địa chỉ. Gate văn phòng; cache RAM 24h/MST; blocking urllib bọc
to_thread. Đăng ký ở app_factory.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import urllib.request

from aiohttp import web

log = logging.getLogger("server")

_CACHE: dict[str, tuple[float, dict]] = {}
_TTL = 24 * 3600


def _fetch(mst: str) -> dict:
    """Gọi VietQR (blocking). Trả {found, name, address, status, active}."""
    req = urllib.request.Request(
        f"https://api.vietqr.io/v2/business/{mst}",
        headers={"User-Agent": "letrang-app/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read())
    data = payload.get("data") or {}
    if str(payload.get("code")) != "00" or not data.get("name"):
        return {"found": False}
    status = str(data.get("status") or "")
    return {
        "found": True,
        "name": str(data.get("name") or ""),
        "address": str(data.get("address") or ""),
        "status": status,
        "active": "đang hoạt động" in status.lower(),
    }


async def mst_lookup_handler(request: web.Request):
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return web.json_response({"ok": False, "error": "Chỉ văn phòng mới tra được MST"}, status=403)
    mst = (request.query.get("mst") or "").replace(" ", "").strip()
    if not re.fullmatch(r"\d{10}(-\d{3})?|\d{12}", mst):
        return web.json_response({"ok": False, "error": "MST không hợp lệ (10 số, 10-3 số hoặc 12 số)"}, status=400)
    hit = _CACHE.get(mst)
    if hit and time.time() - hit[0] < _TTL:
        return web.json_response({"ok": True, **hit[1], "cached": True})
    try:
        info = await asyncio.to_thread(_fetch, mst)
    except Exception as e:
        log.warning("mst lookup lỗi %s: %s", mst, e)
        return web.json_response({"ok": False, "error": "Không tra được MST (dịch vụ tra cứu lỗi/mạng)"}, status=502)
    if len(_CACHE) > 500:
        _CACHE.clear()
    _CACHE[mst] = (time.time(), info)
    return web.json_response({"ok": True, **info})


def register(r) -> None:
    r.add_get("/api/mst-lookup", mst_lookup_handler)
