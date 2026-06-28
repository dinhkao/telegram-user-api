"""bot_don_hang/html_to_png.py — Render invoice HTML to PNG and send as photo.

Minimal port of telegram-user-api/firebase_html_to_png.py (Firebase-free path).
Playwright Chromium browser is initialized once and reused across jobs.
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

from PIL import Image
from playwright.sync_api import sync_playwright

log = logging.getLogger("html_to_png")

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="html_to_png")

# Persistent Playwright browser (reused across jobs)
_playwright = None
_browser = None


def _init_browser():
    """Launch Playwright Chromium once. Called from the worker thread."""
    global _playwright, _browser
    if _browser is not None:
        return
    _playwright = sync_playwright().start()
    _browser = _playwright.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-gpu"],
    )
    log.info("Playwright browser started (persistent)")


def prewarm():
    """Kick off browser init in background so first invoice render isn't slow."""
    _executor.submit(_init_browser)


def _crop_image(input_path: str, output_path: str, margin: int = 5) -> None:
    image = Image.open(input_path)
    if image.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", image.size, (255, 255, 255))
        bg.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
        image = bg
    elif image.mode != "RGB":
        image = image.convert("RGB")

    white = (255, 255, 255)
    width, height = image.size
    left, top, right, bottom = 0, 0, width - 1, height - 1

    while left < width:
        col = [image.getpixel((left, y)) for y in range(height)]
        if any(p != white for p in col):
            break
        left += 1
    while right >= 0:
        col = [image.getpixel((right, y)) for y in range(height)]
        if any(p != white for p in col):
            break
        right -= 1
    while top < height:
        row = [image.getpixel((x, top)) for x in range(width)]
        if any(p != white for p in row):
            break
        top += 1
    while bottom >= 0:
        row = [image.getpixel((x, bottom)) for x in range(width)]
        if any(p != white for p in row):
            break
        bottom -= 1

    if left < right and top < bottom:
        left = max(0, left - margin)
        top = max(0, top - margin)
        right = min(width - 1, right + margin)
        bottom = min(height - 1, bottom + margin)
        image = image.crop((left, top, right + 1, bottom + 1))

    image.save(output_path, "PNG")


def _html_to_png(html_content: str) -> str:
    """Convert HTML → cropped PNG path. Lazily inits Playwright on first call."""
    if _browser is None:
        _init_browser()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
        f.write(html_content)
        html_path = f.name

    screenshot_path = tempfile.mktemp(suffix=".png")
    output_path = tempfile.mktemp(suffix=".png")

    try:
        page = _browser.new_page()
        page.set_viewport_size({"width": 360, "height": 600})
        page.goto(f"file://{os.path.abspath(html_path)}", wait_until="load")
        page.wait_for_timeout(100)
        page.screenshot(path=screenshot_path, full_page=True)
        page.close()
        _crop_image(screenshot_path, output_path)
        return output_path
    finally:
        for p in (html_path, screenshot_path):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass


async def render_and_send_html(bot, html: str, chat_id: int,
                               reply_to: int | None = None,
                               caption: str = "",
                               parse_mode: str = "html") -> str | None:
    """Render HTML → PNG and send photo via bot. Returns photo path on success."""
    loop = asyncio.get_running_loop()
    photo_path = await loop.run_in_executor(_executor, _html_to_png, html)
    try:
        await bot.send_file(chat_id, photo_path, reply_to=reply_to,
                             caption=caption, parse_mode=parse_mode)
        return photo_path
    finally:
        if photo_path and os.path.exists(photo_path):
            try:
                os.remove(photo_path)
            except OSError:
                pass
