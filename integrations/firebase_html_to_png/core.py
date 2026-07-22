from __future__ import annotations

import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

# 1 worker DUY NHẤT: Playwright sync API trói browser vào thread khởi tạo nó —
# nhiều worker → job rơi thread khác ném "Cannot switch to a different thread".
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="html_to_png")
_playwright = None
_browser = None


def _init_browser(log):
    from playwright.sync_api import sync_playwright

    global _playwright, _browser
    if _browser is not None:
        try:
            if _browser.is_connected():
                return
        except Exception:
            pass
        _browser = None
    if _playwright is not None:
        try:
            _playwright.stop()
        except Exception:
            pass
        _playwright = None
    _playwright = sync_playwright().start()
    _browser = _playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
    log.info("Playwright browser started (persistent)")


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
    while left < width and all(image.getpixel((left, y)) == white for y in range(height)):
        left += 1
    while right >= 0 and all(image.getpixel((right, y)) == white for y in range(height)):
        right -= 1
    while top < height and all(image.getpixel((x, top)) == white for x in range(width)):
        top += 1
    while bottom >= 0 and all(image.getpixel((x, bottom)) == white for x in range(width)):
        bottom -= 1
    if left < right and top < bottom:
        image = image.crop((max(0, left - margin), max(0, top - margin), min(width - 1, right + margin) + 1, min(height - 1, bottom + margin) + 1))
    image.save(output_path, "PNG")


def _html_to_png(html_content: str, log, viewport_width: int = 360, wait_ms: int = 100) -> str:
    global _browser
    if _browser is None:
        _init_browser(log)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
        f.write(html_content)
        html_path = f.name
    screenshot_path = tempfile.mktemp(suffix=".png")
    output_path = tempfile.mktemp(suffix=".png")
    try:
        for attempt in range(2):
            try:
                page = _browser.new_page()
                page.set_viewport_size({"width": max(360, int(viewport_width)), "height": 600})
                page.goto(f"file://{os.path.abspath(html_path)}", wait_until="load")
                if wait_ms > 0:
                    page.wait_for_timeout(int(wait_ms))
                page.screenshot(path=screenshot_path, full_page=True)
                page.close()
                _crop_image(screenshot_path, output_path)
                return output_path
            except Exception as e:
                if "closed" in str(e).lower() or "target" in str(e).lower():
                    log.warning("Browser closed/crashed on attempt %d, reinitializing...", attempt + 1)
                    _browser = None
                    _init_browser(log)
                    if attempt == 0:
                        continue
                raise
    finally:
        for p in (html_path, screenshot_path):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
