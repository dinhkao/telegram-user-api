"""bot_core/html_to_png.py — Render invoice HTML to PNG and send as photo."""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

from playwright.sync_api import sync_playwright

log = logging.getLogger("html_to_png")

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="html_to_png")
_playwright = None
_browser = None


def _init_browser():
    """Launch Playwright Chromium once."""
    global _playwright, _browser
    if _browser is not None:
        return
    _playwright = sync_playwright().start()
    _browser = _playwright.chromium.launch(
        headless=True, args=["--no-sandbox", "--disable-gpu"],
    )
    log.info("Playwright browser started (persistent)")


def prewarm():
    """Kick off browser init in background."""
    _executor.submit(_init_browser)


def _html_to_png(html_content: str) -> str:
    """Convert HTML → cropped PNG path."""
    from bot_core.image_crop import crop_image
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
        crop_image(screenshot_path, output_path)
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
    """Render HTML → PNG and send photo via bot."""
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
