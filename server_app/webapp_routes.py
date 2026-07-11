"""Serve web app quản lý đơn (webapp/dist — Vite+Preact build) tại /app.

Hash routing phía client → chỉ cần index.html + assets. Chưa build (thiếu
webapp/dist) thì trả 404 hướng dẫn thay vì crash lúc đăng ký route.
Đăng ký ở server_app/app_factory. Build: `cd webapp && npm run build`.

Cache-Control: index.html = no-cache (luôn revalidate qua ETag → không bao giờ
kẹt bản cũ trỏ tới asset hash đã bị xoá = màn hình trắng sau khi build lại).
Asset có hash trong tên → immutable, cache 1 năm (đổi build là đổi hash).
"""
from __future__ import annotations

import os

from aiohttp import web

_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "webapp", "dist")
_ASSETS = os.path.join(_DIST, "assets")
# Thư mục chứa APK + version.json cho tự cập nhật (builder deploy vào đây).
_APK_DIR = os.path.expanduser(os.getenv("WEBAPP_APK_DIR", "~/letrang-db/apk"))


async def app_version_handler(request: web.Request):
    """Manifest cập nhật cho APK — {versionCode, versionName, url}. 404 nếu chưa deploy."""
    vf = os.path.join(_APK_DIR, "version.json")
    if not os.path.isfile(vf):
        return web.json_response({"versionCode": 0}, headers={"Cache-Control": "no-cache"})
    resp = web.FileResponse(vf)
    resp.headers["Cache-Control"] = "no-cache, must-revalidate"
    return resp


async def app_apk_handler(request: web.Request):
    """Tải APK mới nhất để tự cập nhật."""
    apk = os.path.join(_APK_DIR, "app.apk")
    if not os.path.isfile(apk):
        return web.Response(status=404, text="no apk")
    resp = web.FileResponse(apk)
    resp.headers["Content-Type"] = "application/vnd.android.package-archive"
    return resp


async def webapp_index_handler(request: web.Request):
    index = os.path.join(_DIST, "index.html")
    if not os.path.isfile(index):
        return web.Response(status=404, text="Chưa build web app: cd webapp && npm run build")
    resp = web.FileResponse(index)
    # luôn hỏi lại server (rẻ: 304 nhờ ETag) → không phục vụ index.html cũ
    resp.headers["Cache-Control"] = "no-cache, must-revalidate"
    return resp


async def webapp_asset_handler(request: web.Request):
    rel = request.match_info.get("path", "")
    full = os.path.normpath(os.path.join(_ASSETS, rel))
    # chặn path traversal (../ ra ngoài thư mục assets)
    if full != _ASSETS and not full.startswith(_ASSETS + os.sep):
        return web.Response(status=403, text="forbidden")
    if not os.path.isfile(full):
        return web.Response(status=404, text="not found")
    resp = web.FileResponse(full)
    # tên file có hash nội dung → an toàn để cache vĩnh viễn
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


async def app_reload_handler(request: web.Request):
    """ÉP mọi client web đang mở tải lại (lấy bundle mới). POST /api/app/reload.
    Trả số client đang kết nối. Chỉ tới được máy ĐÃ có bản có listener app_reload."""
    from server_app.realtime import emit_app_reload
    from server_app.state import ws_clients
    n = len(ws_clients)
    emit_app_reload()
    return web.json_response({"ok": True, "clients": n})


async def _redirect_to_slash(request: web.Request):
    # base './' trong bundle → phải có dấu / cuối để ./assets resolve đúng /app/assets
    raise web.HTTPMovedPermanently("/app/")


def register_webapp_routes(router) -> None:
    router.add_get("/app", _redirect_to_slash)
    router.add_get("/app/", webapp_index_handler)
    # tạo sẵn thư mục để server start trước khi build web không lỗi —
    # build xong là serve được ngay, không cần restart
    os.makedirs(_ASSETS, exist_ok=True)
    router.add_get("/app/assets/{path:.*}", webapp_asset_handler)
    # Tự cập nhật APK: builder deploy version.json + app.apk vào WEBAPP_APK_DIR
    os.makedirs(_APK_DIR, exist_ok=True)
    router.add_get("/app/update/version.json", app_version_handler)
    router.add_get("/app/update/app.apk", app_apk_handler)
    router.add_post("/api/app/reload", app_reload_handler)   # admin ép mọi máy tải lại
