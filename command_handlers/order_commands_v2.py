from __future__ import annotations

from .order_commands_v2_admin import register_order_commands_v2_admin
from .order_commands_v2_customer import register_order_commands_v2_customer
from .order_commands_v2_debug import register_order_commands_v2_debug
from .order_commands_v2_detect import register_order_commands_v2_detect


def register_order_commands_v2(client):
    register_order_commands_v2_customer(client)
    register_order_commands_v2_detect(client)
    register_order_commands_v2_admin(client)
    register_order_commands_v2_debug(client)
