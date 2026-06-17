"""firebase_html_to_png.py — Firebase RTDB html-to-png listener.

Converts HTML to PNG via Playwright, crops whitespace with Pillow,
and sends the photo via the Telethon user account (not a bot).

Listens on Firebase path: html-to-png
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

from PIL import Image
from playwright.sync_api import sync_playwright
from firebase_admin import db

log = logging.getLogger("html_to_png")

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="html_to_png")

# Persistent Playwright browser (reused across jobs)
_playwright = None
_browser = None


def _init_browser():
    """Launch Playwright once (in a thread, since we're inside asyncio)."""
    global _playwright, _browser
    if _browser is not None:
        return
    _playwright = sync_playwright().start()
    _browser = _playwright.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-gpu"],
    )
    log.info("Playwright browser started (persistent)")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _normalize(data: dict):
    discussion_group_id = data.get("discussion_group_id")
    discussion_thread_id = data.get("discussion_group_thread_id")
    discussion_message_id = data.get("discussion_group_message_id")
    discussion_main_message_id = data.get("discussion_group_main_message_id")

    chat_id = discussion_group_id or data.get("chat_id")
    message_thread_id = (
        discussion_thread_id or discussion_message_id or data.get("message_thread_id")
    )
    reply_to_message_id = discussion_main_message_id or data.get("reply_to_message_id")

    is_discussion = any(
        x is not None
        for x in [
            discussion_group_id,
            discussion_thread_id,
            discussion_message_id,
            discussion_main_message_id,
        ]
    )

    return {
        "html": data.get("html"),
        "chat_id": chat_id,
        "message_thread_id": message_thread_id,
        "reply_to_message_id": reply_to_message_id,
        "is_discussion": is_discussion,
        "caption": data.get("caption"),
        "parse_mode": data.get("parse_mode"),
    }


def _crop_image(input_path: str, output_path: str, margin: int = 5) -> None:
    image = Image.open(input_path)
    if image.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", image.size, (255, 255, 255))
        bg.paste(
            image,
            mask=image.split()[-1] if image.mode == "RGBA" else None,
        )
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
    """Convert HTML string → cropped PNG. Returns path to PNG file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
        f.write(html_content)
        html_path = f.name

    screenshot_path = tempfile.mktemp(suffix=".png")
    output_path = tempfile.mktemp(suffix=".png")

    try:
        page = _browser.new_page()
        page.set_viewport_size({"width": 360, "height": 600})
        page.goto(f"file://{os.path.abspath(html_path)}", wait_until="load")
        # Wait just enough for fonts/images to settle
        page.wait_for_timeout(100)
        page.screenshot(path=screenshot_path, full_page=True)
        page.close()

        _crop_image(screenshot_path, output_path)
        return output_path
    except Exception:
        raise
    finally:
        for p in (html_path, screenshot_path):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass


async def _send_photo(client, chat_id, photo_path, reply_to, message_thread_id, caption, parse_mode):
    entity = await client.get_entity(chat_id)
    # In forum topics, message_thread_id is the top message ID of the topic.
    # We must reply to that message (or use it as reply_to) for the photo
    # to land inside the correct topic instead of the General topic.
    reply_to_id = reply_to or message_thread_id
    await client.send_file(
        entity,
        photo_path,
        reply_to=reply_to_id,
        caption=caption,
        parse_mode=parse_mode,
    )
    log.info("Sent photo to %s (reply_to=%s thread=%s)", chat_id, reply_to, message_thread_id)


def _process_job_sync(client, loop, ref, key, job):
    """Runs inside the thread-pool."""
    if not job["html"] or not job["chat_id"]:
        log.warning("Missing html or chat_id — skipping")
        return

    if job["is_discussion"] and not job["message_thread_id"]:
        log.warning("Discussion job missing message_thread_id — skipping")
        return

    photo_path = None
    try:
        photo_path = _html_to_png(job["html"])
        future = asyncio.run_coroutine_threadsafe(
            _send_photo(
                client,
                job["chat_id"],
                photo_path,
                job["reply_to_message_id"],
                job["message_thread_id"],
                job["caption"],
                job["parse_mode"],
            ),
            loop,
        )
        future.result(timeout=60)
    except Exception as e:
        log.error("Job %s failed: %s", key or "single", e)
        return
    finally:
        if photo_path and os.path.exists(photo_path):
            try:
                os.remove(photo_path)
            except Exception:
                pass

    # Cleanup Firebase
    try:
        if key:
            ref.child(key).delete()
        else:
            ref.update({
                "html": None,
                "chat_id": None,
                "message_thread_id": None,
                "reply_to_message_id": None,
                "discussion_group_id": None,
                "discussion_group_thread_id": None,
                "discussion_group_message_id": None,
                "discussion_group_main_message_id": None,
            })
    except Exception as e:
        log.warning("Firebase cleanup failed: %s", e)


# ─── Public entry point ──────────────────────────────────────────────────────

def start_listener(client, fb_app=None):
    from firebase_sync import _get_app

    app = fb_app or _get_app()
    if not app:
        log.warning("Firebase not available — html-to-png listener disabled")
        return

    loop = asyncio.get_running_loop()
    # Launch Playwright browser in a thread (sync API incompatible with asyncio loop)
    _executor.submit(_init_browser).result(timeout=30)
    ref = db.reference("html-to-png", app=app)
    first_event = True

    def _on_event(event):
        nonlocal first_event
        if first_event:
            log.info("Skipping initial firebase event…")
            first_event = False
            return

        data = event.data
        if not data:
            return

        # Child event (e.g. path == /pushId)
        path = event.path or "/"
        if path != "/" and isinstance(data, dict):
            key = path.lstrip("/")
            job = _normalize(data)
            _executor.submit(_process_job_sync, client, loop, ref, key, job)
            return

        # Root event: read current snapshot to process batch
        try:
            all_data = ref.get()
        except Exception as e:
            log.error("Failed to read firebase ref: %s", e)
            return

        if not all_data or not isinstance(all_data, dict):
            return

        # Detect single job vs batch of child jobs
        looks_single = (
            ("html" in all_data or "chat_id" in all_data)
            and not any(
                isinstance(v, dict) and ("html" in v or "chat_id" in v)
                for v in all_data.values()
                if isinstance(v, dict)
            )
        )

        if looks_single:
            job = _normalize(all_data)
            if job["html"] and job["chat_id"]:
                _executor.submit(_process_job_sync, client, loop, ref, None, job)
            return

        for key, child in all_data.items():
            if isinstance(child, dict):
                job = _normalize(child)
                if job["html"] and job["chat_id"]:
                    _executor.submit(_process_job_sync, client, loop, ref, key, job)

    ref.listen(_on_event)
    log.info("Firebase html-to-png listener started")
