"""ĐĂNG XUẤT gỡ thông báo của máy — POST /api/fcm/unregister (server_app.fcm_routes).

Chốt: đăng xuất xong máy KHÔNG còn đứng tên user đó (hết nhận push, kể cả trao đổi
LƯƠNG chỉ văn phòng); user khác biết token cũng không gỡ được máy người ta; chưa đăng
nhập → 401. Chạy trên DB tạm (vá fcm_routes.get_connection) — không đụng app.db thật.
"""
from __future__ import annotations

import os
import tempfile

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

import server_app.fcm_routes as fr
from notif_store.fcm_tokens import ensure_table
from utils.db import get_connection


class FcmUnregisterRouteTest(AioHTTPTestCase):
    async def get_application(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        conn = get_connection(self.path)
        ensure_table(conn)
        conn.close()
        self._orig = fr.get_connection
        fr.get_connection = lambda *a, **k: get_connection(self.path)
        self.who = {"user": "trang"}

        @web.middleware
        async def fake_auth(request, handler):   # giả web_auth: user lấy từ token
            if self.who["user"]:
                request["web_user"] = self.who["user"]
            return await handler(request)

        app = web.Application(middlewares=[fake_auth])
        app.router.add_post("/api/fcm/register", fr.fcm_register_handler)
        app.router.add_post("/api/fcm/unregister", fr.fcm_unregister_handler)
        return app

    async def tearDownAsync(self):
        fr.get_connection = self._orig
        os.unlink(self.path)

    def _rows(self):
        conn = get_connection(self.path)
        try:
            return {r[0]: r[1] for r in conn.execute("SELECT token, username FROM fcm_tokens")}
        finally:
            conn.close()

    async def test_dang_xuat_go_may_khoi_user(self):
        self.who["user"] = "trang"
        self.assertEqual((await self.client.post("/api/fcm/register", json={"token": "tokA"})).status, 200)
        self.assertEqual(self._rows(), {"tokA": "trang"})
        # người khác (biết token) không gỡ được máy của trang
        self.who["user"] = "thao"
        d = await (await self.client.post("/api/fcm/unregister", json={"token": "tokA"})).json()
        self.assertEqual(d["removed"], 0)
        self.assertEqual(self._rows(), {"tokA": "trang"})
        # chính trang đăng xuất → máy thôi đứng tên trang
        self.who["user"] = "trang"
        d = await (await self.client.post("/api/fcm/unregister", json={"token": "tokA"})).json()
        self.assertEqual((d["ok"], d["removed"]), (True, 1))
        self.assertEqual(self._rows(), {})

    async def test_chua_dang_nhap_va_token_rong(self):
        self.who["user"] = None
        self.assertEqual((await self.client.post("/api/fcm/unregister", json={"token": "x"})).status, 401)
        self.who["user"] = "trang"
        self.assertEqual((await self.client.post("/api/fcm/unregister", json={})).status, 400)
