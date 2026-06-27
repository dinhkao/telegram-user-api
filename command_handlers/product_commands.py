from __future__ import annotations

from .product_commands_manage import register_product_commands_manage
from .product_commands_profit import register_product_commands_profit


def register_product_commands(client):
    register_product_commands_manage(client)
    register_product_commands_profit(client)
