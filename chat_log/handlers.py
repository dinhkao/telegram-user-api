from .db import ORDER_GROUP_ID, init_table
from .deleted_message import attach_deleted_message_handler
from .edited_message import attach_edited_message_handler
from .new_message import attach_new_message_handler


def register_chat_logger(client) -> None:
    init_table()
    attach_new_message_handler(client)
    attach_edited_message_handler(client)
    attach_deleted_message_handler(client)
