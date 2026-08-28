"""Endpoint /ws — kênh realtime cho webapp (đơn thay đổi / danh sách thay đổi).

Chỉ giữ danh sách client đang kết nối trong state.ws_clients; nội dung đẩy do
server_app/realtime.py phát. heartbeat giữ kết nối sống qua mobile/Tailscale.
Client (webapp/src/realtime.ts) chỉ nhận, không gửi lệnh gì (tin nhắn vào bị bỏ qua).
Ngay khi mở, server gửi {"type":"hello","build":...} = build id webapp đang phục vụ
(server_app/app_build.py) để máy đang chạy bundle CŨ tự tải lại.
Kèm ws_ping_loop (spawn từ bootstrap): phát {"type":"ping"} app-level mỗi 25s —
ping/pong protocol-level của aiohttp browser JS KHÔNG thấy được, client cần tin
nhắn thật để watchdog phát hiện socket "nửa sống" (WebView suspend, TCP đứt không FIN).
"""
from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from server_app import state
from server_app.config import WEB_AUTH_ENABLED

log = logging.getLogger("server")

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}

_PING_INTERVAL = 25  # giây — client coi im lặng >65s (2 nhịp + dư) là socket chết


async def ws_ping_loop() -> None:
    """Keepalive chạy suốt đời process. Không có client → _send return sớm, gần như
    0 chi phí. Client lỗi do _send_one của realtime.py tự đóng + loại khỏi danh sách."""
    from server_app.realtime import _send
    while True:
        await asyncio.sleep(_PING_INTERVAL)
        try:
            await _send({"type": "ping"})
        except Exception as e:  # noqa: BLE001 — keepalive không được chết vì 1 nhịp lỗi
            log.warning("ws ping loop: %s", e)


async def websocket_handler(request: web.Request):
    # Khi bật chặn: /ws đẩy PII (khách, sđt, tiền) nên phải có token hợp lệ.
    # Middleware đã giải ?token= → request["web_user"]; loopback THẬT (bot role) miễn
    # — qua tailscale serve/funnel remote luôn là 127.0.0.1 nên phải lấy IP thật
    # từ X-Forwarded-For (web_auth.middleware.effective_remote), không thì Funnel
    # mở là cả internet nghe được kênh realtime.
    from server_app.web_auth.middleware import effective_remote
    if WEB_AUTH_ENABLED and "web_user" not in request and \
            effective_remote(request.remote, request.headers) not in _LOOPBACK:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)
    # "hello" mang BUILD ID webapp server đang phục vụ. Client so với bundle của
    # chính nó → máy chạy bản cũ (WebView sống nhiều ngày) tự tải lại. Gửi TRƯỚC
    # khi vào vòng nhận; client bản cũ không biết type này thì bỏ qua, vô hại.
    from server_app.app_build import build_id
    bid = build_id()
    if bid:
        try:
            await ws.send_json({"type": "hello", "build": bid})
        except Exception as e:  # noqa: BLE001 — socket hỏng ngay lúc mở, để vòng dưới dọn
            log.warning("WS hello: %s", e)
    state.ws_clients.add(ws)
    # Vai trò bó hẹp chat_luong (middleware đã giải token → web_role): đánh dấu để
    # vòng phát chỉ gửi event trang chất lượng — order_changed/notif_added mang PII
    # đơn/khách/tiền không được đổ về máy họ.
    from server_app.web_auth.role_scope import QUALITY_ONLY_ROLE
    if request.get("web_role") == QUALITY_ONLY_ROLE:
        state.ws_quality_only.add(ws)
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.ERROR:
                log.warning("WS error: %s", ws.exception())
            # client không cần gửi gì — mọi tin nhắn vào đều bỏ qua
    finally:
        state.ws_clients.discard(ws)
        state.ws_quality_only.discard(ws)
    return ws
