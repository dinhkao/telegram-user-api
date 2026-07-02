"""Endpoint /ws — kênh realtime cho webapp (đơn thay đổi / danh sách thay đổi).

Chỉ giữ danh sách client đang kết nối trong state.ws_clients; nội dung đẩy do
server_app/realtime.py phát. heartbeat giữ kết nối sống qua mobile/Tailscale.
Client (webapp/src/realtime.ts) chỉ nhận, không gửi lệnh gì (tin nhắn vào bị bỏ qua).
"""
from __future__ import annotations

import logging

from aiohttp import web

from server_app import state
from server_app.config import WEB_AUTH_ENABLED

log = logging.getLogger("server")

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


async def websocket_handler(request: web.Request):
    # Khi bật chặn: /ws đẩy PII (khách, sđt, tiền) nên phải có token hợp lệ.
    # Middleware đã giải ?token= → request["web_user"]; loopback (bot role) miễn.
    if WEB_AUTH_ENABLED and "web_user" not in request and request.remote not in _LOOPBACK:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)
    state.ws_clients.add(ws)
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.ERROR:
                log.warning("WS error: %s", ws.exception())
            # client không cần gửi gì — mọi tin nhắn vào đều bỏ qua
    finally:
        state.ws_clients.discard(ws)
    return ws
