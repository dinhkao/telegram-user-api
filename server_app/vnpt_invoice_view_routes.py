"""Bản thể hiện hoá đơn nháp VNPT: PDF tải về + PNG xem ngay trong app.

Tách khỏi server_app/vnpt_invoice_routes.py (CRUD nháp) cho gọn file. PDF/HTML
lấy từ PortalService (integrations/vnpt_invoice/portal.py); PNG render qua đúng
pipeline Playwright của ảnh HĐ KiotViet. Chỉ văn phòng.
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from order_db import _get_connection, get_order_by_thread_id

from integrations.vnpt_invoice.core import VnptError

log = logging.getLogger("server")


def _tid(request: web.Request) -> int | None:
    raw = request.match_info.get("thread_id", "").strip()
    return int(raw) if raw.lstrip("-").isdigit() else None


async def _draft_for_view(request: web.Request) -> tuple[dict | None, web.Response | None]:
    """(draft đã synced, None) hoặc (None, response lỗi) — gate office + 3 bước tra đơn."""
    from server_app.order_api_common import is_office_request
    if not await is_office_request(request):
        return None, web.Response(text="Chỉ văn phòng mới xem được HĐ điện tử", status=403)
    tid = _tid(request)
    if tid is None:
        return None, web.Response(text="thread_id không hợp lệ", status=400)
    order = get_order_by_thread_id(_get_connection(), tid)
    if not order:
        return None, web.Response(text="Không tìm thấy đơn", status=404)
    draft = order.get("vnpt_invoice") or {}
    if not (draft.get("synced") and draft.get("fkey")):
        return None, web.Response(text="Đơn chưa có HĐ điện tử nháp — tạo nháp trước.", status=400)
    return draft, None

async def vnpt_invoice_pdf_handler(request: web.Request):
    """GET .../vnpt-invoice/pdf — tải PDF bản thể hiện nháp từ VNPT (văn phòng).
    Mở tab mới kèm ?token= như invoice-html; Số HĐ trên PDF = 00000000 (chưa phát hành)."""
    draft, err = await _draft_for_view(request)
    if err:
        return err
    tid = _tid(request)
    from integrations.vnpt_invoice import download_draft_pdf
    try:
        pdf = await asyncio.to_thread(download_draft_pdf, draft["fkey"])
    except VnptError as e:
        log.error("vnpt pdf failed tid=%s fkey=%s: %s", tid, draft.get("fkey"), e)
        return web.Response(text=f"Lỗi tải PDF từ VNPT: {e}", status=502)
    return web.Response(
        body=pdf, content_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="HD-nhap-{tid}.pdf"'})


# PNG bản thể hiện nháp — cache theo fkey (fkey ĐỔI mỗi lần lưu nên cache tự
# đúng, không cần invalidation); render Playwright ~1-2s nên cache đáng tiền.
_png_cache: dict[str, bytes] = {}


async def vnpt_invoice_png_handler(request: web.Request):
    """GET .../vnpt-invoice/png — ảnh PNG bản thể hiện nháp để XEM NGAY TRONG APP
    (WebView không render PDF). HTML từ VNPT (getNewInvViewFkey) → PNG qua đúng
    pipeline Playwright của ảnh HĐ KiotViet (integrations/firebase_html_to_png)."""
    draft, err = await _draft_for_view(request)
    if err:
        return err
    tid, fkey = _tid(request), draft["fkey"]
    png = _png_cache.get(fkey)
    if png is None:
        from integrations.vnpt_invoice import get_draft_view_html
        try:
            html = await asyncio.to_thread(get_draft_view_html, fkey)
        except VnptError as e:
            log.error("vnpt png: lấy HTML lỗi tid=%s fkey=%s: %s", tid, fkey, e)
            return web.Response(text=f"Lỗi lấy bản xem từ VNPT: {e}", status=502)
        import os
        from integrations.firebase_html_to_png.core import _executor, _html_to_png
        from server_app.invoice_image import _read_bytes
        png_path = None
        try:
            loop = asyncio.get_running_loop()
            # viewport 900px: bản thể hiện VNPT là khổ A4 (mặc định 360px là bể layout)
            png_path = await loop.run_in_executor(_executor, _html_to_png, html, log, 900, 300)
            png = await asyncio.to_thread(_read_bytes, png_path)
        except Exception as e:  # noqa: BLE001
            log.error("vnpt png: render lỗi tid=%s: %s", tid, e)
            return web.Response(text="Lỗi render ảnh hoá đơn — thử lại", status=502)
        finally:
            if png_path:
                try:
                    os.unlink(png_path)
                except OSError:
                    pass
        if len(_png_cache) > 20:
            _png_cache.clear()
        _png_cache[fkey] = png
    # no-store: URL cố định theo đơn nhưng nội dung đổi theo fkey — để browser cache
    # là sửa nháp xong 5' vẫn thấy ảnh cũ; tốc độ đã có RAM cache theo fkey lo.
    return web.Response(body=png, content_type="image/png",
                        headers={"Cache-Control": "no-store"})


def register_vnpt_invoice_view_routes(r) -> None:
    r.add_get("/api/order/{thread_id}/vnpt-invoice/pdf", vnpt_invoice_pdf_handler)
    r.add_get("/api/order/{thread_id}/vnpt-invoice/png", vnpt_invoice_png_handler)
