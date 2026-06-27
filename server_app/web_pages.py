from __future__ import annotations

from aiohttp import web


async def index_handler(request: web.Request):
    return web.FileResponse("static/index.html")
