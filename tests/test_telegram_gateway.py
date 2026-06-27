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
            exc = self.send_message_failures.pop(0)
            raise exc
        return _Result(id=101, kind="send_message", **kwargs)

    async def edit_message(self, **kwargs):
        self.calls.append(("edit_message", kwargs, time.perf_counter()))
        if self.edit_message_failures:
            exc = self.edit_message_failures.pop(0)
            raise exc
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


class TelegramGatewayTest(unittest.IsolatedAsyncioTestCase):
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

    async def test_other_wrappers_passthrough(self):
        client = FakeClient()
        gateway = tg.TelegramGateway(
            client,
            global_rate_per_sec=1000,
            per_chat_rate_per_sec=1000,
        )

        sent = await gateway.send_file(11, "file.txt", caption="cap")
        deleted = await gateway.delete_messages(11, [1, 2, 3], revoke=True)
        fetched = await gateway.get_messages(11, limit=5)

        self.assertEqual(sent.kind, "send_file")
        self.assertTrue(deleted.ok)
        self.assertEqual(fetched.kind, "get_messages")
        self.assertEqual([c[0] for c in client.calls], ["send_file", "delete_messages", "get_messages"])

    async def test_install_routes_client_methods_without_recursion(self):
        client = FakeClient()
        gateway = tg.TelegramGateway(
            client,
            global_rate_per_sec=1000,
            per_chat_rate_per_sec=1000,
        )
        gateway.install()

        result = await client.send_message(123, "hello")

        self.assertEqual(result.kind, "send_message")
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0][1]["message"], "hello")

    async def test_per_chat_rate_limit_spacing(self):
        client = FakeClient()
        gateway = tg.TelegramGateway(
            client,
            global_rate_per_sec=1000,
            per_chat_rate_per_sec=20,
        )

        await gateway.send_message(777, "one")
        await gateway.send_message(777, "two")

        first_call = client.calls[0][2]
        second_call = client.calls[1][2]
        self.assertGreaterEqual(second_call - first_call, 0.04)


if __name__ == "__main__":
    unittest.main()
