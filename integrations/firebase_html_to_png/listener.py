import asyncio
import logging

from .core import _executor
from .jobs import _normalize, _process_job_sync

log = logging.getLogger("html_to_png")


def start_listener(client, fb_app=None):
    from ..firebase_png_print import ref as png_ref, _get_app as _get_png_app

    try:
        app = fb_app or _get_png_app()
    except Exception as e:
        log.warning("Firebase init failed: %s — html-to-png listener disabled", e)
        return
    if not app:
        log.warning("Firebase not available — html-to-png listener disabled")
        return
    loop = asyncio.get_running_loop()
    log.info("html-to-png listener: browser will init on first job")
    ref = png_ref("html-to-png")
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
        path = event.path or "/"
        if path != "/" and isinstance(data, dict):
            _executor.submit(_process_job_sync, client, loop, ref, path.lstrip("/"), _normalize(data))
            return
        try:
            all_data = ref.get()
        except Exception as e:
            log.error("Failed to read firebase ref: %s", e)
            return
        if not all_data or not isinstance(all_data, dict):
            return
        looks_single = ("html" in all_data or "chat_id" in all_data) and not any(
            isinstance(v, dict) and ("html" in v or "chat_id" in v) for v in all_data.values() if isinstance(v, dict)
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

    try:
        ref.listen(_on_event)
        log.info("Firebase html-to-png listener started")
    except Exception as e:
        log.warning("Firebase listen failed: %s — html-to-png listener disabled", e)
