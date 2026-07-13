import asyncio
import time
import unittest
from unittest.mock import patch

from server_app import cloudinary_routes, cloudinary_warm
from server_app.audit import _NO_AUDIT
from server_app.cloudinary_routes import _camera_image, _decode_cursor, _delivery_variant, _encode_cursor, _get_cloudinary_page, _normalize_iso_time, _search_expression


class CloudinaryRoutesTest(unittest.TestCase):
    def test_delivery_variant_keeps_credentials_out_and_adds_transform(self):
        url = "https://res.cloudinary.com/demo/image/upload/v1/camera_2026/a.jpg"
        self.assertEqual(
            _delivery_variant(url, "f_auto,q_auto,w_640"),
            "https://res.cloudinary.com/demo/image/upload/f_auto,q_auto,w_640/v1/camera_2026/a.jpg",
        )

    def test_camera_image_exposes_only_safe_gallery_fields(self):
        image = _camera_image({
            "asset_id": "asset-1",
            "public_id": "camera_2026/cam-01",
            "resource_type": "image",
            "type": "upload",
            "secure_url": "https://res.cloudinary.com/demo/image/upload/v1/camera_2026/cam-01.jpg",
            "width": 1920,
            "height": 1080,
            "bytes": 12345,
            "created_at": "2026-07-13T07:00:00Z",
            "api_key": "must-not-leak",
        })
        self.assertEqual(image["id"], "main:asset-1")
        self.assertEqual(image["name"], "cam-01")
        self.assertNotIn("api_key", image)
        self.assertIn("q_auto:low", image["thumbnail_url"])
        self.assertIn("w_480", image["thumbnail_url"])
        self.assertNotIn("g_auto", image["thumbnail_url"])
        self.assertIn("c_limit", image["preview_url"])
        self.assertIn("q_auto:eco", image["preview_url"])
        self.assertIn("w_1280", image["preview_url"])

    def test_non_image_asset_is_ignored(self):
        self.assertIsNone(_camera_image({"resource_type": "video", "type": "upload"}))

    def test_multi_account_cursor_round_trip(self):
        state = {"main": "cursor-one", "camera_2": None}
        encoded = _encode_cursor(state)
        self.assertIsNotNone(encoded)
        self.assertEqual(_decode_cursor(encoded), state)
        self.assertNotIn("cursor-one", encoded)

    def test_searches_both_camera_subfolders(self):
        expression = _search_expression(
            {"folder": "camera_2026"}, None, "folder",
            "2026-07-12T17:00:00Z", "2026-07-13T16:59:59Z",
        )
        self.assertIn('folder="camera_2026/channel_11"', expression)
        self.assertIn('folder="camera_2026/channel_14"', expression)
        self.assertIn("resource_type:image", expression)
        self.assertIn('created_at>="2026-07-12T17:00:00Z"', expression)
        self.assertIn('created_at<="2026-07-13T16:59:59Z"', expression)

    def test_normalizes_client_time_to_utc(self):
        self.assertEqual(_normalize_iso_time("2026-07-13T10:30:00+07:00"), "2026-07-13T03:30:00Z")

    def test_camera_poll_is_excluded_from_audit(self):
        self.assertIsNotNone(_NO_AUDIT.search("/api/cloudinary/camera-images"))
        self.assertIsNone(_NO_AUDIT.search("/api/orders"))
        self.assertIsNone(_NO_AUDIT.search("/api/cloudinary/other"))


_ACCOUNT = {"id": "main", "label": "MAIN", "cloud_name": "demo",
            "api_key": "k", "api_secret": "s", "folder": "camera_2026"}


class FirstPageCacheTest(unittest.IsolatedAsyncioTestCase):
    """Stale-while-revalidate + dedup của _get_cloudinary_page (mock _fetch_page)."""

    def setUp(self):
        cloudinary_routes._FIRST_PAGE_CACHE.clear()
        cloudinary_routes._INFLIGHT.clear()
        cloudinary_routes._FOLDER_FIELD.clear()

    def _fake_fetch(self, data, delay=0.0):
        calls = []

        async def fetch(account, cursor, channel=None, created_from=None, created_to=None):
            calls.append(account["id"])
            if delay:
                await asyncio.sleep(delay)
            return dict(data)

        return fetch, calls

    async def test_swr_returns_stale_and_schedules_single_refresh(self):
        key = "main:*"
        cloudinary_routes._FIRST_PAGE_CACHE[key] = (time.monotonic() - 120, {"marker": "old"})
        fetch, calls = self._fake_fetch({"marker": "new"}, delay=0.01)
        with patch.object(cloudinary_routes, "_fetch_page", fetch):
            results = await asyncio.gather(*[_get_cloudinary_page(_ACCOUNT, None) for _ in range(3)])
            self.assertTrue(all(r["marker"] == "old" for r in results))  # trả bản cũ NGAY
            await cloudinary_routes._INFLIGHT[key]  # chờ refresh nền
        self.assertEqual(calls, ["main"])  # 3 request stale → đúng 1 fetch
        self.assertEqual(cloudinary_routes._FIRST_PAGE_CACHE[key][1]["marker"], "new")

    async def test_cold_key_dedups_concurrent_fetches(self):
        fetch, calls = self._fake_fetch({"marker": "fresh"}, delay=0.01)
        with patch.object(cloudinary_routes, "_fetch_page", fetch):
            results = await asyncio.gather(*[_get_cloudinary_page(_ACCOUNT, None) for _ in range(4)])
        self.assertTrue(all(r["marker"] == "fresh" for r in results))
        self.assertEqual(calls, ["main"])

    async def test_hard_stale_fetches_synchronously(self):
        key = "main:*"
        cloudinary_routes._FIRST_PAGE_CACHE[key] = (
            time.monotonic() - cloudinary_routes._STALE_MAX_SECONDS - 10, {"marker": "ancient"})
        fetch, calls = self._fake_fetch({"marker": "new"})
        with patch.object(cloudinary_routes, "_fetch_page", fetch):
            result = await _get_cloudinary_page(_ACCOUNT, None)
        self.assertEqual(result["marker"], "new")  # không trả bản quá cũ
        self.assertEqual(calls, ["main"])

    async def test_cursor_and_time_range_bypass_cache(self):
        cloudinary_routes._FIRST_PAGE_CACHE["main:*"] = (time.monotonic(), {"marker": "cached"})
        fetch, calls = self._fake_fetch({"marker": "direct"})
        with patch.object(cloudinary_routes, "_fetch_page", fetch):
            by_cursor = await _get_cloudinary_page(_ACCOUNT, "abc")
            by_range = await _get_cloudinary_page(_ACCOUNT, None, None, "2026-07-01T00:00:00Z", None)
        self.assertEqual(by_cursor["marker"], "direct")
        self.assertEqual(by_range["marker"], "direct")
        self.assertEqual(len(calls), 2)


class _SearchResponse:
    def __init__(self, status, data):
        self.status = status
        self._data = data

    async def json(self, content_type=None):
        return self._data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _SearchSession:
    """Giả lập account dynamic-folder: field `folder` trả 400, `asset_folder` trả 200."""

    def __init__(self):
        self.expressions = []

    def post(self, url, json=None, auth=None):
        expression = json["expression"]
        self.expressions.append(expression)
        if "asset_folder=" not in expression:
            return _SearchResponse(400, {"error": "folder not supported"})
        return _SearchResponse(200, {"resources": [], "next_cursor": None})


class FolderFieldMemoTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        cloudinary_routes._FOLDER_FIELD.clear()

    async def test_folder_field_memo_skips_400_retry(self):
        session = _SearchSession()

        async def fake_get_session():
            return session

        with patch.object(cloudinary_warm, "get_session", fake_get_session):
            await cloudinary_routes._fetch_page(_ACCOUNT, None)
            self.assertEqual(len(session.expressions), 2)  # lần đầu: 400 rồi retry
            self.assertEqual(cloudinary_routes._FOLDER_FIELD["main"], "asset_folder")
            await cloudinary_routes._fetch_page(_ACCOUNT, None)
        self.assertEqual(len(session.expressions), 3)  # lần sau: gọi thẳng, không retry
        self.assertIn("asset_folder=", session.expressions[-1])


if __name__ == "__main__":
    unittest.main()
