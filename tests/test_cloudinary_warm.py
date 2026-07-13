"""Test server_app/cloudinary_warm.py: chọn URL warm, track warmed FIFO, best-effort."""
import unittest
from unittest.mock import patch

from server_app import cloudinary_warm


def _image(i: int) -> dict:
    return {
        "id": f"main:asset-{i}",
        "thumbnail_url": f"https://res.cloudinary.com/demo/image/upload/t/{i}.jpg",
        "preview_url": f"https://res.cloudinary.com/demo/image/upload/p/{i}.jpg",
    }


def _reset() -> None:
    cloudinary_warm._warmed.clear()
    cloudinary_warm._warmed_q.clear()


class WarmedSetTest(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_warmed_set_evicts_fifo_and_stays_in_sync(self):
        cloudinary_warm.seed_warmed(f"id-{i}" for i in range(cloudinary_warm._WARMED_MAX + 5))
        self.assertEqual(len(cloudinary_warm._warmed), cloudinary_warm._WARMED_MAX)
        self.assertEqual(set(cloudinary_warm._warmed_q), cloudinary_warm._warmed)
        for i in range(5):  # 5 id cũ nhất bị đẩy ra
            self.assertNotIn(f"id-{i}", cloudinary_warm._warmed)
        self.assertIn("id-5", cloudinary_warm._warmed)

    def test_seed_warmed_marks_without_fetch(self):
        images = [_image(i) for i in range(3)]
        cloudinary_warm.seed_warmed(image["id"] for image in images)
        self.assertEqual(cloudinary_warm.collect_warm_urls(images), [])

    def test_collect_warm_urls_skips_warmed_and_caps_cycle(self):
        cloudinary_warm.seed_warmed(["main:asset-0"])
        images = [_image(i) for i in range(40)]
        pairs = cloudinary_warm.collect_warm_urls(images)
        self.assertLessEqual(len(pairs), cloudinary_warm._CYCLE_CAP)
        urls = [url for _, url in pairs]
        self.assertNotIn(_image(0)["thumbnail_url"], urls)  # đã warm → bỏ qua
        # Preview chỉ cho _PREVIEW_TOP ảnh mới chưa warm đầu tiên (1..4), từ ảnh 5 chỉ thumb.
        previews = [url for url in urls if "/p/" in url]
        self.assertEqual(previews, [_image(i)["preview_url"] for i in range(1, 1 + cloudinary_warm._PREVIEW_TOP)])
        self.assertIn(_image(1)["thumbnail_url"], urls)


class _FakeContent:
    async def iter_chunked(self, size):
        yield b"x"


class _FakeResponse:
    def __init__(self):
        self.status = 404  # 4xx = lỗi vĩnh viễn → vẫn coi là warm xong
        self.content = _FakeContent()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _FakeSession:
    def __init__(self, fail_urls=()):
        self.fail_urls = set(fail_urls)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        if url in self.fail_urls:
            raise OSError("network down")
        return _FakeResponse()


class WarmUrlsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _reset()

    async def test_marks_on_http_response_not_on_network_error(self):
        ok, bad = _image(1), _image(2)
        session = _FakeSession(fail_urls={bad["thumbnail_url"]})

        async def fake_get_session():
            return session

        with patch.object(cloudinary_warm, "get_session", fake_get_session):
            await cloudinary_warm.warm_urls([
                (ok["id"], ok["thumbnail_url"]),
                (bad["id"], bad["thumbnail_url"]),
            ])
        self.assertIn(ok["id"], cloudinary_warm._warmed)
        self.assertNotIn(bad["id"], cloudinary_warm._warmed)  # chu kỳ sau thử lại

    async def test_id_with_failed_preview_is_not_marked(self):
        image = _image(3)
        session = _FakeSession(fail_urls={image["preview_url"]})

        async def fake_get_session():
            return session

        with patch.object(cloudinary_warm, "get_session", fake_get_session):
            await cloudinary_warm.warm_urls([
                (image["id"], image["thumbnail_url"]),
                (image["id"], image["preview_url"]),
            ])
        self.assertNotIn(image["id"], cloudinary_warm._warmed)


if __name__ == "__main__":
    unittest.main()
