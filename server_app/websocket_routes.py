"""Endpoint /ws — kênh realtime cho webapp (đơn thay đổi / danh sách thay đổi).

Chỉ giữ danh sách client đang kết nối trong state.ws_clients; nội dung đẩy do
server_app/realtime.py phát. heartbeat giữ kết nối sống qua mobile/Tailscale.
Client (webapp/src/realtime.ts) chỉ nhận, không gửi lệnh gì (tin nhắn vào bị bỏ qua).
"""
from __future__ import annotations

import logging

from aiohttp import web

from server_app import state

log = logging.getLogger("server")


async def websocket_handler(request: web.Request):
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
