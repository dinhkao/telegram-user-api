from __future__ import annotations

import asyncio
import logging

from audit_log import async_log_event

log = logging.getLogger("server")


def spawn_tracked(name: str, coro, context: dict | None = None) -> asyncio.Task:
    task = asyncio.create_task(coro, name=name)
    ctx = context or {}

    def _done(done_task: asyncio.Task) -> None:
        try:
            done_task.result()
            log.debug("background task ok: %s context=%s", name, ctx)
        except asyncio.CancelledError:
            log.warning("background task cancelled: %s context=%s", name, ctx)
        except Exception as exc:
            log.exception("background task failed: %s context=%s", name, ctx)
            try:
                asyncio.get_running_loop().create_task(async_log_event(
                    "background_task.error", actor_type="server", source=name, payload=ctx, error=exc
                ))
            except RuntimeError:
                pass

    task.add_done_callback(_done)
    return task
