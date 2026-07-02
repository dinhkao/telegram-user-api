"""Route gốc `/` — chuyển hướng sang webapp `/app/`.

Trang saved-messages cũ (static/index.html) đã bỏ; webapp là UI web duy nhất.
"""
from __future__ import annotations

from aiohttp import web


async def index_handler(request: web.Request):
    raise web.HTTPFound("/app/")
