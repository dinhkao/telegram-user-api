from __future__ import annotations

import json
import logging

from aiohttp import web

from server_app import state

log = logging.getLogger("server")


async def websocket_handler(request: web.Request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    state.ws_clients.add(ws)
    await ws.send_str(json.dumps({"type": "history", "messages": state.recent_messages}, default=str))
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT and msg.data == "history":
                await ws.send_str(json.dumps({"type": "history", "messages": state.recent_messages}, default=str))
            elif msg.type == web.WSMsgType.ERROR:
                log.warning("WS error: %s", ws.exception())
    finally:
        state.ws_clients.discard(ws)
    return ws
