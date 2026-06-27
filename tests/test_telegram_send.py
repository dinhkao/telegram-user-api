import asyncio
import time
import unittest
from unittest.mock import patch

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


class TelegramGatewaySendTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_message_retries_flood_wait(self):
        client = FakeClient()
        client.send_message_failures = [tg.FloodWaitError(request=None, capture=1)]
        gateway = tg.TelegramGateway(
            client,
            global_rate_per_sec=1000,
            per_chat_rate_per_sec=1000,
            flood_max_sleep_sec=5,
        )
        sleep_calls = []

        async def fake_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("telegram_gateway.asyncio.sleep", new=fake_sleep):
            result = await gateway.send_message(123, "hello")

        self.assertEqual(result.id, 101)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(sleep_calls, [1])

    async def test_send_message_raises_when_flood_wait_is_too_large(self):
        client = FakeClient()
        client.send_message_failures = [tg.FloodWaitError(request=None, capture=10)]
        gateway = tg.TelegramGateway(
            client,
            global_rate_per_sec=1000,
            per_chat_rate_per_sec=1000,
            flood_max_sleep_sec=3,
        )

        with self.assertRaises(tg.TelegramRateLimited) as ctx:
            await gateway.send_message(123, "hello")

        self.assertEqual(ctx.exception.seconds, 10)
        self.assertEqual(len(client.calls), 1)
