from __future__ import annotations

from order_db import _get_connection

from .order_commands_add import register_order_commands_add
from .order_commands_clear import register_order_commands_clear
from .order_commands_done import register_order_commands_done
from .order_commands_skip import register_order_commands_skip


def register_order_commands(client):
    db_conn = _get_connection()
    register_order_commands_done(client, db_conn)
    register_order_commands_clear(client, db_conn)
    register_order_commands_add(client, db_conn)
    register_order_commands_skip(client, db_conn)
