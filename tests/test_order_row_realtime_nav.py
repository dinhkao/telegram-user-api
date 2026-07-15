import json
import unittest
from unittest.mock import patch

from server_app.orders_api import _build_order_row


class OrderRowRealtimeNavTest(unittest.TestCase):
    @patch("order_store.display.display_maps", return_value=None)
    def test_row_exposes_customer_key_for_realtime_nav_membership(self, _display_maps):
        row = {
            "firebase_key": "order-key",
            "thread_id": 123,
            "channel_id": 1,
            "message_id": 2,
            "updated_at": 3,
            "json": json.dumps({"khach_hang_id": "customer-42"}),
        }

        result = _build_order_row(row)

        self.assertEqual(result["customer_key"], "customer-42")


if __name__ == "__main__":
    unittest.main()
