from __future__ import annotations

import logging

from .analysis import register_analysis_handlers
from .customer import register_customer_handlers
from .debt import register_debt_handlers
from .invoice import register_invoice_handlers
from .payment import _handle_payment  # re-exported via __init__
from .print import register_print_handlers
from .refresh import _EditBatcher, set_edit_batcher

log = logging.getLogger("order_commands_v3")


def register_order_commands_v3(client):
    from order_db import _get_connection

    db_conn = _get_connection()
    set_edit_batcher(_EditBatcher(client, db_conn, delay=3.0))
    log.info("order_commands_v3 listening")
    register_customer_handlers(client, db_conn)
    register_invoice_handlers(client, db_conn)
    register_print_handlers(client, db_conn)
    register_debt_handlers(client, db_conn)
    register_analysis_handlers(client, db_conn)
