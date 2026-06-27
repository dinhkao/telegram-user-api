from __future__ import annotations

import asyncio
from typing import Any

from .edit_state import EditState
from .errors import MessageNotModifiedError
from .operations import run_operation


async def edit_message(gateway: Any, entity: Any, message_id: int | None = None, text: Any = None, **kwargs: Any) -> Any:
    if message_id is None:
        message_id = kwargs.pop("message")
    else:
        kwargs.pop("message", None)
    if text is None and "text" in kwargs:
        text = kwargs.pop("text")
    key = gateway._edit_key(entity, message_id)
    loop = asyncio.get_running_loop()
    async with gateway._ensure_edit_states_lock():
        state = gateway._edit_states.get(key)
        if state is None:
            state = EditState()
            gateway._edit_states[key] = state
        state.version += 1
        state.entity = entity
        state.message_id = int(message_id)
        state.text = text
        state.kwargs = dict(kwargs)
        if state.future is None or state.future.done():
            state.future = loop.create_future()
        if state.runner is None or state.runner.done():
            state.runner = loop.create_task(run_edit_task(gateway, key))
        future = state.future
    return await future


async def run_edit_task(gateway: Any, key: tuple[Any, int]) -> None:
    while True:
        await asyncio.sleep(gateway.edit_debounce_sec)
        async with gateway._ensure_edit_states_lock():
            state = gateway._edit_states.get(key)
            if state is None:
                return
            version = state.version
            entity = state.entity
            message_id = state.message_id
            text = state.text
            kwargs = dict(state.kwargs)
            future = state.future
        operation = f"edit_message[{message_id}]"
        error: Exception | None = None
        result: Any = None
        try:
            result = await run_operation(
                operation,
                entity,
                gateway._acquire_rate_limit,
                lambda: gateway._orig_edit_message(entity=entity, message=message_id, text=text, **kwargs),
                gateway.flood_max_sleep_sec,
            )
        except MessageNotModifiedError:
            result = None
        except Exception as exc:
            error = exc
        async with gateway._ensure_edit_states_lock():
            state = gateway._edit_states.get(key)
            if state is None:
                return
            if state.version != version:
                continue
            gateway._edit_states.pop(key, None)
            if future is not None and not future.done():
                if error is None:
                    future.set_result(result)
                else:
                    future.set_exception(error)
            return


__all__ = ["edit_message", "run_edit_task"]
