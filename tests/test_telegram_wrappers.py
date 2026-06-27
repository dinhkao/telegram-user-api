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

    async def send_message(self, **kwargs):
        self.calls.append(("send_message", kwargs, time.perf_counter()))
        return _Result(id=101, kind="send_message", **kwargs)


class TelegramGatewayWrapperTests(unittest.IsolatedAsyncioTestCase):
    async def test_other_wrappers_passthrough(self):
        client = FakeClient()
        gateway = tg.TelegramGateway(client, global_rate_per_sec=1000, per_chat_rate_per_sec=1000)
        sent = await gateway.send_file(11, "file.txt", caption="cap")
        deleted = await gateway.delete_messages(11, [1, 2, 3], revoke=True)
        fetched = await gateway.get_messages(11, limit=5)

        self.assertEqual(sent.kind, "send_file")
        self.assertTrue(deleted.ok)
        self.assertEqual(fetched.kind, "get_messages")
        self.assertEqual([c[0] for c in client.calls], ["send_file", "delete_messages", "get_messages"])

    async def test_install_routes_client_methods_without_recursion(self):
        client = FakeClient()
        gateway = tg.TelegramGateway(client, global_rate_per_sec=1000, per_chat_rate_per_sec=1000)
        gateway.install()
        result = await client.send_message(123, "hello")

        self.assertEqual(result.kind, "send_message")
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0][1]["message"], "hello")

    async def test_per_chat_rate_limit_spacing(self):
        client = FakeClient()
        gateway = tg.TelegramGateway(client, global_rate_per_sec=1000, per_chat_rate_per_sec=20)
        await gateway.send_message(777, "one")
        await gateway.send_message(777, "two")

        first_call = client.calls[0][2]
        second_call = client.calls[1][2]
        self.assertGreaterEqual(second_call - first_call, 0.04)
