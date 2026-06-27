from __future__ import annotations

from server_app import state


async def tg_send_message(entity, message, **kwargs):
    client = state._tg_gateway or state._client
    return await (state._tg_gateway.send_message(entity, message, **kwargs) if state._tg_gateway else client.send_message(entity, message, **kwargs))


async def tg_edit_message(entity, message, text=None, **kwargs):
    client = state._tg_gateway or state._client
    return await (state._tg_gateway.edit_message(entity=entity, message=message, text=text, **kwargs) if state._tg_gateway else client.edit_message(entity=entity, message=message, text=text, **kwargs))


async def tg_delete_messages(entity, message_ids, **kwargs):
    return await (state._tg_gateway.delete_messages(entity, message_ids, **kwargs) if state._tg_gateway else state._client.delete_messages(entity, message_ids, **kwargs))


async def tg_get_messages(entity, **kwargs):
    return await (state._tg_gateway.get_messages(entity, **kwargs) if state._tg_gateway else state._client.get_messages(entity, **kwargs))
