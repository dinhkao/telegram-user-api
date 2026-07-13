"""Session HTTP dùng chung + CDN warming cho gallery camera Cloudinary.

Dùng bởi server_app/cloudinary_routes.py: 1 ClientSession chung (keep-alive cho cả
Search API lẫn res.cloudinary.com) và chủ động "warm" derived asset (thumb/preview)
của ảnh MỚI ngay khi refresher thấy — tới lúc user xem thì CDN đã có sẵn, không phải
chờ Cloudinary derive (0.5-3s). Không ghi disk; RAM chỉ set id đã warm (bounded).
"""
from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Iterable

import aiohttp

# f_auto derive THEO Accept header — phải gửi giống browser, không thì Cloudinary tạo
# bản JPEG còn browser (nhận AVIF/WebP) vẫn phải cold-derive khi xem → warm vô dụng.
_ACCEPT = "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"
_WARMED_MAX = 500  # ~vài trang đầu của mọi account; FIFO evict
_CYCLE_CAP = 20    # tối đa URL warm mỗi chu kỳ refresher (phần dư chờ chu kỳ sau)
_PREVIEW_TOP = 4   # chỉ warm preview (w_1280, derive chậm nhất) cho vài ảnh mới nhất

_session: aiohttp.ClientSession | None = None
_warmed: set[str] = set()
_warmed_q: deque[str] = deque()


async def get_session() -> aiohttp.ClientSession:
    """Session chung, tạo lười. BasicAuth đưa vào TỪNG request (multi-account)."""
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15, connect=5),
            connector=aiohttp.TCPConnector(limit=10),
        )
    return _session


async def close_session() -> None:
    if _session is not None and not _session.closed:
        await _session.close()


def _mark(image_id: str) -> None:
    if image_id in _warmed:
        return
    _warmed.add(image_id)
    _warmed_q.append(image_id)
    while len(_warmed_q) > _WARMED_MAX:
        _warmed.discard(_warmed_q.popleft())


def seed_warmed(image_ids: Iterable[str]) -> None:
    """Đánh dấu ảnh cũ lúc boot là đã warm mà KHÔNG fetch — derived asset của chúng
    gần như chắc chắn đã có từ lần xem trước; tránh burst request mỗi lần restart."""
    for image_id in image_ids:
        _mark(image_id)


def collect_warm_urls(images: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Chọn (id, url) cần warm từ list ảnh đã sort mới→cũ. Pure để unit-test:
    thumbnail cho mọi ảnh chưa warm, preview thêm cho _PREVIEW_TOP ảnh mới nhất,
    tổng không quá _CYCLE_CAP URL."""
    out: list[tuple[str, str]] = []
    rank = 0
    for image in images:
        if image["id"] in _warmed:
            continue
        if len(out) >= _CYCLE_CAP:
            break
        out.append((image["id"], image["thumbnail_url"]))
        if rank < _PREVIEW_TOP and len(out) < _CYCLE_CAP:
            out.append((image["id"], image["preview_url"]))
        rank += 1
    return out


async def warm_urls(pairs: list[tuple[str, str]]) -> None:
    """GET từng URL, bỏ body theo chunk (đỉnh 64KB RAM, không ghi disk). Best-effort:
    có HTTP response (kể cả 4xx = lỗi vĩnh viễn) là warm xong; lỗi mạng/timeout thì
    KHÔNG mark để chu kỳ sau thử lại. Nuốt lỗi im lặng."""
    if not pairs:
        return
    semaphore = asyncio.Semaphore(4)
    done: set[str] = set()
    failed: set[str] = set()

    async def fetch_one(image_id: str, url: str) -> None:
        async with semaphore:
            try:
                session = await get_session()
                async with session.get(
                    url, headers={"Accept": _ACCEPT},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    async for _ in response.content.iter_chunked(65536):
                        pass
                done.add(image_id)
            except Exception:
                failed.add(image_id)

    await asyncio.gather(*[fetch_one(image_id, url) for image_id, url in pairs])
    for image_id in done - failed:  # id có cả thumb+preview: phải xong hết mới mark
        _mark(image_id)
