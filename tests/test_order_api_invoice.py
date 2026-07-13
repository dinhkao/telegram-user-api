import json
import unittest
from contextlib import nullcontext
from unittest.mock import AsyncMock, Mock, patch

from server_app import state
from server_app.order_api_invoice import api_delete_invoice_handler, api_set_invoice_reference_image_handler


class _Request(dict):
    def __init__(self, body=None):
        super().__init__()
        self.body = body or {"thread_id": 123, "user_id": "duy"}

    async def json(self):
        return self.body


class DeleteInvoiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_delete_kiotviet_invoice_undoes_ban_hd_task(self):
        order = {
            "kiotvietInvoiceID": 456,
            "kiotvietInvoiceCode": "HD000456",
            "task_status": {"ban_hd": {"done": True}},
        }
        conn = Mock()

        with (
            patch("server_app.order_api_invoice.apply_web_actor"),
            patch("server_app.order_api_invoice._is_admin", AsyncMock(return_value=True)),
            patch("server_app.order_api_invoice._get_connection", return_value=conn),
            patch("server_app.order_api_invoice.get_order_by_thread_id", return_value=order),
            patch("kiotviet.delete_invoice_kv") as delete_invoice,
            patch("server_app.order_api_invoice._save_order") as save_order,
            patch("server_app.order_api_invoice.set_task_status") as set_task,
            patch("order_images_store.list_images", return_value=[]),
            patch.object(state, "_client", None),
        ):
            response = await api_delete_invoice_handler(_Request())

        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.body), {"ok": True, "thread_id": 123})
        delete_invoice.assert_called_once_with(456)
        save_order.assert_called_once_with(conn, 123, order)
        set_task.assert_called_once_with(conn, 123, "ban_hd", "duy", done=False)
        self.assertNotIn("kiotvietInvoiceID", order)
        self.assertNotIn("kiotvietInvoiceCode", order)


class InvoiceReferenceImageTests(unittest.IsolatedAsyncioTestCase):
    async def test_saves_image_from_same_order(self):
        order = {"thread_id": 123}
        conn = Mock()
        with (
            patch("server_app.order_api_invoice.apply_web_actor"),
            patch("server_app.order_api_invoice._get_connection", return_value=conn),
            patch("server_app.order_api_invoice.get_order_by_thread_id", return_value=order),
            patch("server_app.order_api_invoice.transaction", return_value=nullcontext()),
            patch("server_app.order_api_invoice._save_order", return_value=True) as save_order,
            patch("order_images_store.get_image", return_value={"id": 77, "thread_id": 123, "deleted_at": None}),
            patch("server_app.realtime.emit_order_changed") as emit_changed,
        ):
            response = await api_set_invoice_reference_image_handler(_Request({"thread_id": 123, "image_id": 77}))

        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.body)["image_id"], 77)
        self.assertEqual(order["invoice_reference_image_id"], 77)
        save_order.assert_called_once_with(conn, 123, order)
        emit_changed.assert_called_once_with(123)

    async def test_rejects_image_from_another_order(self):
        with (
            patch("server_app.order_api_invoice.apply_web_actor"),
            patch("order_images_store.get_image", return_value={"id": 77, "thread_id": 999, "deleted_at": None}),
            patch("server_app.order_api_invoice._save_order") as save_order,
        ):
            response = await api_set_invoice_reference_image_handler(_Request({"thread_id": 123, "image_id": 77}))

        self.assertEqual(response.status, 400)
        save_order.assert_not_called()

    async def test_clears_saved_reference(self):
        order = {"invoice_reference_image_id": 77}
        conn = Mock()
        with (
            patch("server_app.order_api_invoice.apply_web_actor"),
            patch("server_app.order_api_invoice._get_connection", return_value=conn),
            patch("server_app.order_api_invoice.get_order_by_thread_id", return_value=order),
            patch("server_app.order_api_invoice.transaction", return_value=nullcontext()),
            patch("server_app.order_api_invoice._save_order", return_value=True),
            patch("server_app.realtime.emit_order_changed"),
        ):
            response = await api_set_invoice_reference_image_handler(_Request({"thread_id": 123, "image_id": None}))

        self.assertEqual(response.status, 200)
        self.assertNotIn("invoice_reference_image_id", order)
