import asyncio
import time
import unittest

import telegram_gateway as tg


class _Result:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeClient:
    def __init__(self):
        self.calls = []
        self.send_message_failures = []
        self.edit_message_failures = []

    async def send_message(self, **kwargs):
        self.calls.append(("send_message", kwargs, time.perf_counter()))
        if self.send_message_failures:
            raise self.send_message_failures.pop(0)
        return _Result(id=101, kind="send_message", **kwargs)

    async def edit_message(self, **kwargs):
        self.calls.append(("edit_message", kwargs, time.perf_counter()))
        if self.edit_message_failures:
            raise self.edit_message_failures.pop(0)
        payload = dict(kwargs)
        payload["id"] = kwargs["message"]
        payload["kind"] = "edit_message"
        payload["text"] = kwargs["text"]
        return _Result(**payload)

    async def send_file(self, **kwargs):
        self.calls.append(("send_file", kwargs, time.perf_counter()))
        return _Result(id=202, kind="send_file", **kwargs)

    async def delete_messages(self, entity, message_ids, **kwargs):
        payload = {"entity": entity, "message_ids": message_ids, **kwargs}
        self.calls.append(("delete_messages", payload, time.perf_counter()))
        return _Result(ok=True, kind="delete_messages", **payload)

    async def get_messages(self, entity, **kwargs):
        payload = {"entity": entity, **kwargs}
        self.calls.append(("get_messages", payload, time.perf_counter()))
        return _Result(kind="get_messages", **payload)


class TelegramGatewayEditTests(unittest.IsolatedAsyncioTestCase):
    async def test_edit_message_debounces_and_keeps_last_payload(self):
        client = FakeClient()
        gateway = tg.TelegramGateway(
            client,
            global_rate_per_sec=1000,
            per_chat_rate_per_sec=1000,
            edit_debounce_sec=0.03,
        )
        first = asyncio.create_task(gateway.edit_message(123, 55, "draft-1"))
        await asyncio.sleep(0.01)
        second = asyncio.create_task(gateway.edit_message(123, 55, "draft-2"))
        res1, res2 = await asyncio.gather(first, second)

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0][0], "edit_message")
        self.assertEqual(client.calls[0][1]["text"], "draft-2")
        self.assertEqual(res1.text, "draft-2")
        self.assertEqual(res2.text, "draft-2")

    async def test_edit_message_accepts_telethon_keyword_shape(self):
        client = FakeClient()
        gateway = tg.TelegramGateway(
            client,
            global_rate_per_sec=1000,
            per_chat_rate_per_sec=1000,
            edit_debounce_sec=0,
        )
        result = await gateway.edit_message(entity=123, message=55, text="updated")

        self.assertEqual(result.id, 55)
        self.assertEqual(client.calls[0][1]["text"], "updated")
