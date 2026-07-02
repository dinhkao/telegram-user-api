"""Serve web app quản lý đơn (webapp/dist — Vite+Preact build) tại /app.

Hash routing phía client → chỉ cần index.html + assets. Chưa build (thiếu
webapp/dist) thì trả 404 hướng dẫn thay vì crash lúc đăng ký route.
Đăng ký ở server_app/app_factory. Build: `cd webapp && npm run build`.
"""
from __future__ import annotations

import os

from aiohttp import web

_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "webapp", "dist")


def webapp_dist_exists() -> bool:
    return os.path.isfile(os.path.join(_DIST, "index.html"))


async def webapp_index_handler(request: web.Request):
    index = os.path.join(_DIST, "index.html")
    if not os.path.isfile(index):
        return web.Response(status=404, text="Chưa build web app: cd webapp && npm run build")
    return web.FileResponse(index)


async def _redirect_to_slash(request: web.Request):
    # base './' trong bundle → phải có dấu / cuối để ./assets resolve đúng /app/assets
    raise web.HTTPMovedPermanently("/app/")


def register_webapp_routes(router) -> None:
    router.add_get("/app", _redirect_to_slash)
    router.add_get("/app/", webapp_index_handler)
    if os.path.isdir(os.path.join(_DIST, "assets")):
        router.add_static("/app/assets/", os.path.join(_DIST, "assets"))
