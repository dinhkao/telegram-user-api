"""API GIẤY DÁN THÙNG của 1 đơn — /api/order/{tid}/gdt (GET/POST), .../gdt/print,
.../gdt/png (xem trước), .../gdt/html. Ghi blob đơn `$.giay_dan_thung` (chung key
với lệnh Telegram `gdt`/`ingdt` ở command_handlers/gdt_handler.py) + nhớ tên/SĐT
người nhận theo khách (`$.gdt_contact`). IN = đẩy HTML vào Firebase `meta/to_print`
y như hoá đơn/phiếu giao (printouts/common.queue_html_for_print) — cùng máy in
nhiệt 80mm; kèm gửi file HTML vào topic đơn để in tay được khi máy in offline.
Luật thuần: server_app/gdt_domain.py; HTML: renderers/giay_dan_thung.py.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import tempfile

from aiohttp import web

from order_db import _get_connection, _save_order, get_customer_by_key, get_order_by_thread_id, transaction
from order_store.customers import update_customer
from printouts.common import queue_html_for_print
from renderers.giay_dan_thung import GDT_SENDER, generate_gdt_html
from server_app import state
from server_app.config import ORDER_GROUP_ID
from server_app.gdt_domain import build_prefill, contact_from, gdt_of, normalize_body, summary
from server_app.order_api_common import apply_web_actor, resolve_name
from server_app.order_api_mutations import _invoice_total, _paid_total
from server_app.tasks import spawn_tracked

log = logging.getLogger("server")
PRINT_PATH = "meta/to_print"   # cùng hàng đợi với hoá đơn + phiếu giao
MAX_COPIES = 5


def _tid(request: web.Request) -> int | None:
    raw = request.match_info.get("thread_id", "").strip()
    return int(raw) if raw.lstrip("-").isdigit() else None


def _err(msg: str, status: int = 400) -> web.Response:
    return web.json_response({"ok": False, "error": msg}, status=status)


def _customer_key(order: dict) -> str | None:
    key = order.get("khach_hang_id") or order.get("khID")
    return str(key) if key else None


def _load(request: web.Request):
    tid = _tid(request)
    if tid is None:
        return None, None, _err("thread_id không hợp lệ")
    conn = _get_connection()
    order = get_order_by_thread_id(conn, tid)
    if not order:
        return tid, None, _err("Không tìm thấy đơn", 404)
    return tid, order, None


def _remaining(order: dict) -> int:
    total = _invoice_total(order.get("invoice"), order.get("vat"), order.get("pvc"), order.get("discount"))
    return max(0, total - _paid_total(order))


async def gdt_get_handler(request: web.Request):
    tid, order, err = _load(request)
    if err:
        return err
    conn = _get_connection()
    key = _customer_key(order)
    customer = get_customer_by_key(conn, key) if key else None
    return web.json_response({
        "ok": True,
        "gdt": gdt_of(order),
        "prefill": build_prefill(order, customer, _remaining(order)),
        "sender": GDT_SENDER,
    })


def _save_gdt(conn, tid: int, gdt: dict) -> dict:
    """RMW blob trong transaction (đơn đổi song song không mất) + cache khách."""
    with transaction(conn):
        fresh = get_order_by_thread_id(conn, tid) or {}
        fresh["giay_dan_thung"] = gdt
        _save_order(conn, tid, fresh)
    key = _customer_key(fresh)
    if key:
        cust = get_customer_by_key(conn, key)
        if cust is not None:
            cust["gdt_contact"] = contact_from(gdt)
            update_customer(conn, key, cust)
    return fresh


async def gdt_save_handler(request: web.Request):
    tid, order, err = _load(request)
    if err:
        return err
    body = await request.json()
    apply_web_actor(request, body)
    gdt, bad = normalize_body(body)
    if bad:
        return _err(bad)
    conn = _get_connection()
    _save_gdt(conn, tid, gdt)
    from audit_log import async_log_event
    from server_app.realtime import emit_order_changed
    spawn_tracked("audit.gdt_saved", async_log_event(
        "order.gdt_saved", actor_type="web", actor_id=body.get("user_id"), thread_id=tid,
        payload={**gdt, "created": gdt_of(order) is None}))
    emit_order_changed(tid)
    return web.json_response({"ok": True, "gdt": gdt})


async def enqueue_gdt_print(html: str, copies: int = 1) -> bool:
    """Đẩy HTML nhãn vào hàng đợi máy in (như hoá đơn). False = Firebase chưa cấu hình."""
    from firebase_png_print import ref as fb_ref
    ref = fb_ref(PRINT_PATH)
    if ref is None:
        log.warning("gdt: Firebase chưa cấu hình — không gửi được máy in")
        return False
    return await queue_html_for_print(ref, html, copies)


async def _send_html_to_topic(tid: int, html: str, caption: str) -> None:
    """File HTML vào topic đơn (in tay từ máy tính khi cần) — best-effort."""
    client = state._client
    if client is None:
        return
    path = os.path.join(tempfile.gettempdir(), f"gdt_{tid}.html")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        await client.send_file(ORDER_GROUP_ID, path, caption=caption, reply_to=tid, force_document=True)
    except Exception as e:  # noqa: BLE001
        log.warning("gdt: gửi file HTML vào topic lỗi tid=%s: %s", tid, e)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


async def gdt_print_handler(request: web.Request):
    """POST .../gdt/print {copies?} — body có thể kèm 4 trường để LƯU rồi in 1 phát."""
    tid, order, err = _load(request)
    if err:
        return err
    body = await request.json() if request.can_read_body else {}
    apply_web_actor(request, body)
    conn = _get_connection()
    if body.get("ten") or body.get("ten_gdt"):
        gdt, bad = normalize_body(body)
        if bad:
            return _err(bad)
        _save_gdt(conn, tid, gdt)
        from server_app.realtime import emit_order_changed
        emit_order_changed(tid)
    else:
        gdt = gdt_of(order)
    if not gdt:
        return _err("Chưa có thông tin giấy dán thùng — nhập rồi lưu trước")
    try:
        copies = max(1, min(MAX_COPIES, int(body.get("copies") or 1)))
    except (TypeError, ValueError):
        copies = 1
    html = generate_gdt_html(gdt)
    queued = await enqueue_gdt_print(html, copies)
    if not queued:
        return _err("Máy in chưa cấu hình (Firebase) — không gửi được lệnh in", 503)
    actor = body.get("user_id")
    who = await resolve_name(actor) if actor else "Hệ thống"
    tail = f" ×{copies}" if copies > 1 else ""
    spawn_tracked("gdt.topic_file", _send_html_to_topic(tid, html, f"🖨️ {who} đã in giấy dán thùng{tail} — {summary(gdt)}"))
    from audit_log import async_log_event
    spawn_tracked("audit.gdt_printed", async_log_event(
        "order.gdt_printed", actor_type="web", actor_id=actor, thread_id=tid,
        payload={**gdt, "copies": copies}))
    return web.json_response({"ok": True, "copies": copies, "gdt": gdt})


# Xem trước PNG — cache theo nội dung nhãn (đổi chữ là hash đổi, khỏi invalidation)
_png_cache: dict[str, bytes] = {}


def _gdt_from_query(request: web.Request, order: dict) -> dict | None:
    """Cho phép xem trước NGAY khi đang gõ (chưa lưu): ?ten=&sdt=&so_thung=&note=."""
    q = request.query
    if q.get("ten") or q.get("so_thung"):
        gdt, _ = normalize_body({k: q.get(k, "") for k in ("ten", "sdt", "so_thung", "note")})
        if gdt:
            return gdt
        return {"ten_gdt": q.get("ten", ""), "sdt_gdt": q.get("sdt", ""),
                "so_thung": q.get("so_thung", ""), "note_gdt": q.get("note", "")}
    return gdt_of(order)


async def gdt_png_handler(request: web.Request):
    tid, order, err = _load(request)
    if err:
        return err
    gdt = _gdt_from_query(request, order)
    if not gdt:
        return web.Response(text="Chưa có giấy dán thùng", status=404)
    html = generate_gdt_html(gdt, preview=True)
    key = hashlib.sha1(html.encode("utf-8")).hexdigest()
    png = _png_cache.get(key)
    if png is None:
        from integrations.firebase_html_to_png.core import _executor, _html_to_png
        from server_app.invoice_image import _read_bytes
        png_path = None
        try:
            loop = asyncio.get_running_loop()
            png_path = await loop.run_in_executor(_executor, _html_to_png, html, log, 360, 100)
            png = await asyncio.to_thread(_read_bytes, png_path)
        except Exception as e:  # noqa: BLE001
            log.error("gdt png: render lỗi tid=%s: %s", tid, e)
            return web.Response(text="Lỗi render ảnh xem trước — thử lại", status=502)
        finally:
            if png_path:
                try:
                    os.unlink(png_path)
                except OSError:
                    pass
        if len(_png_cache) > 30:
            _png_cache.clear()
        _png_cache[key] = png
    return web.Response(body=png, content_type="image/png", headers={"Cache-Control": "no-store"})


async def gdt_html_handler(request: web.Request):
    """HTML nhãn (mở tab để in tay từ trình duyệt máy tính)."""
    tid, order, err = _load(request)
    if err:
        return err
    gdt = _gdt_from_query(request, order)
    if not gdt:
        return web.Response(text="Chưa có giấy dán thùng", status=404)
    return web.Response(text=generate_gdt_html(gdt), content_type="text/html", charset="utf-8")


def register_gdt_routes(r) -> None:
    r.add_get("/api/order/{thread_id}/gdt", gdt_get_handler)
    r.add_post("/api/order/{thread_id}/gdt", gdt_save_handler)
    r.add_post("/api/order/{thread_id}/gdt/print", gdt_print_handler)
    r.add_get("/api/order/{thread_id}/gdt/png", gdt_png_handler)
    r.add_get("/api/order/{thread_id}/gdt/html", gdt_html_handler)


__all__ = ["register_gdt_routes", "enqueue_gdt_print"]
