"""TRAO ĐỔI về MỐC LƯƠNG của 1 thợ — scope `worker_moc` của /api/media/*.

Chốt 2 điều:
- entity_id = worker_id ⇒ luồng trao đổi DÙNG CHUNG mọi tháng (đường dẫn không có
  tháng) và tách theo từng thợ.
- Là chuyện TIỀN LƯƠNG ⇒ staff bị 403 cả xem lẫn ghi (như /api/payroll/*), khác các
  scope thường (thùng, phiếu SX…) mở cho mọi người đăng nhập.
"""
from __future__ import annotations

import os
import tempfile
import unittest

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

import server_app.entity_media_routes as em
import server_app.production_wages as pw
from entity_media_store import add_comment as real_add, list_comments as real_list


class WorkerMocCommentsTest(AioHTTPTestCase):
    async def get_application(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        # ⚠ route gọi add_comment/list_comments KHÔNG truyền db_path → mặc định là
        # app.db THẬT. Vá về DB tạm để test không ghi vào dữ liệu thật.
        self._orig = (em.add_comment, em.list_comments, pw.office_user)
        em.add_comment = lambda s, e, u, t: real_add(s, e, u, t, db_path=self.path)
        em.list_comments = lambda s, e: real_list(s, e, db_path=self.path)
        self._office = {"who": True}
        pw.office_user = lambda req: {"username": "vp"} if self._office["who"] else None

        # giả web_auth middleware: gắn request["web_user"] từ token (tên người viết
        # bình luận lấy từ đây, y như chạy thật)
        @web.middleware
        async def fake_auth(request, handler):
            if self._office["who"]:
                request["web_user"] = "vp"
            return await handler(request)

        app = web.Application(middlewares=[fake_auth])
        app.router.add_get("/api/media/{scope}/{entity_id}/comments", em.comments_list_handler)
        app.router.add_post("/api/media/{scope}/{entity_id}/comments", em.comments_add_handler)
        app.router.add_get("/api/media/{scope}/{entity_id}/images", em.images_list_handler)
        return app

    async def tearDownAsync(self):
        em.add_comment, em.list_comments, pw.office_user = self._orig
        os.unlink(self.path)

    async def _post(self, wid: int, text: str):
        return await self.client.post(f"/api/media/worker_moc/{wid}/comments", json={"text": text})

    async def test_van_phong_ghi_va_xem_duoc(self):
        self._office["who"] = True
        r = await self._post(7, "Từ tháng 8 tăng mốc lên 7,5tr")
        self.assertEqual(r.status, 200)
        d = await (await self.client.get("/api/media/worker_moc/7/comments")).json()
        self.assertEqual(len(d["comments"]), 1)
        self.assertEqual(d["comments"][0]["text"], "Từ tháng 8 tăng mốc lên 7,5tr")
        self.assertEqual(d["comments"][0]["username"], "vp")
        self.assertGreater(d["comments"][0]["created_at"], 0)      # có MỐC THỜI GIAN

    async def test_staff_bi_chan_ca_xem_ca_ghi(self):
        self._office["who"] = True
        await self._post(7, "nội dung lương")
        self._office["who"] = False
        self.assertEqual((await self.client.get("/api/media/worker_moc/7/comments")).status, 403)
        self.assertEqual((await self._post(7, "staff ghi")).status, 403)
        self.assertEqual((await self.client.get("/api/media/worker_moc/7/images")).status, 403)
        # scope thường vẫn mở cho staff (không nằm trong _OFFICE_ONLY_SCOPES)
        self.assertEqual((await self.client.get("/api/media/box/7/comments")).status, 200)

    async def test_tach_theo_tho_va_dung_chung_moi_thang(self):
        self._office["who"] = True
        await self._post(7, "ghi chú thợ 7")
        await self._post(9, "ghi chú thợ 9")
        d7 = await (await self.client.get("/api/media/worker_moc/7/comments")).json()
        d9 = await (await self.client.get("/api/media/worker_moc/9/comments")).json()
        self.assertEqual([c["text"] for c in d7["comments"]], ["ghi chú thợ 7"])
        self.assertEqual([c["text"] for c in d9["comments"]], ["ghi chú thợ 9"])
        # đường dẫn KHÔNG có tháng ⇒ mọi tháng của thợ 7 đọc đúng 1 luồng này
        self.assertNotIn("ym", "/api/media/worker_moc/7/comments")

    async def test_scope_la_khong_hop_le_thi_400(self):
        self._office["who"] = True
        r = await self.client.get("/api/media/worker_luong/7/comments")
        self.assertEqual(r.status, 400)


if __name__ == "__main__":
    unittest.main()
