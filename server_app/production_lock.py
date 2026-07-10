"""Khoá phiếu SX: TỰ khoá sau 24h kể từ lúc tạo (date_code = %Y%m%d%H%M%S). Khoá =
chỉ trao đổi (bình luận/ảnh/lịch sử) được, cấm mọi sửa (SP/chỉ tiêu/ghi chú/loại/
số/báo cáo thợ/nhập thùng). Admin ghi đè: lock_override='unlocked' (mở) / 'locked'
(khoá lại) — server_app/production_routes lock/unlock handlers.

Đọc: production_store.get_slip; admin: server_app.order_api_common.is_admin_request.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from aiohttp import web

_VN_TZ = timezone(timedelta(hours=7))
_LOCK_HOURS = 24


def _created(date_code) -> datetime | None:
    try:
        return datetime.strptime(str(date_code), "%Y%m%d%H%M%S").replace(tzinfo=_VN_TZ)
    except (ValueError, TypeError):
        return None


def is_locked(slip: dict | None) -> bool:
    """Phiếu có đang khoá không (theo override admin, hoặc tự-động >24h)."""
    ov = (slip or {}).get("lock_override")
    if ov == "unlocked":
        return False
    if ov == "locked":
        return True
    dt = _created((slip or {}).get("date_code"))
    if dt is None:
        return True   # không rõ ngày tạo (phiếu cũ) → coi như đã khoá
    return datetime.now(_VN_TZ) - dt >= timedelta(hours=_LOCK_HOURS)


def lock_at(slip: dict | None) -> str | None:
    """ISO thời điểm phiếu TỰ khoá (tạo + 24h) khi CÒN đếm ngược; None nếu đã khoá,
    override, hoặc không rõ ngày tạo. Client dùng để hiện 'còn X giờ nữa khoá'."""
    ov = (slip or {}).get("lock_override")
    if ov in ("unlocked", "locked"):
        return None
    dt = _created((slip or {}).get("date_code"))
    if dt is None:
        return None
    deadline = dt + timedelta(hours=_LOCK_HOURS)
    if datetime.now(_VN_TZ) >= deadline:
        return None
    return deadline.isoformat()


def _load_slip(thread_id: int) -> dict | None:
    from production_store import get_slip
    from utils.db import get_connection
    conn = get_connection(readonly=True)
    try:
        return get_slip(conn, thread_id)
    finally:
        conn.close()


async def locked_error(request: web.Request, thread_id: int) -> web.Response | None:
    """Trả 423 nếu phiếu KHOÁ và người gọi KHÔNG phải admin; None nếu được sửa.
    Gọi ở đầu mọi handler SỬA phiếu SX."""
    from server_app.order_api_common import is_admin_request
    if await is_admin_request(request):
        return None
    slip = await asyncio.to_thread(_load_slip, thread_id)
    if slip and is_locked(slip):
        return web.json_response(
            {"ok": False, "error": "Phiếu SX đã khoá (quá 24h) — chỉ trao đổi được. Nhờ admin mở khoá."},
            status=423)
    return None
