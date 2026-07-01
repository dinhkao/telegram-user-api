from __future__ import annotations

from server_app.saved_messages import register_handlers as register_saved_messages


def register_command_handlers(client):
    from what_data import register_what_data_handler
    from gtr_handler import register_gtr_handler
    from order_commands import register_order_commands
    from order_commands_v2 import register_order_commands_v2
    from order_commands_v3 import register_order_commands_v3
    from channel_handler import register as register_channel_handler
    from gdt_handler import register_gdt_handler
    from newkh_handler import register_newkh_handler
    from khachhang_commands import register_khachhang_commands
    from product_commands import register_product_commands
    from order_chat_logger import register_chat_logger
    from command_handlers.production_commands import register_production_commands
    from command_handlers.bang_gia_commands import register_bang_gia_commands
    from command_handlers.note_commands import register_note_commands
    from command_handlers.quy_commands import register_quy_commands
    for fn in [register_what_data_handler, register_gtr_handler, register_order_commands, register_order_commands_v2, register_order_commands_v3, register_channel_handler, register_gdt_handler, register_newkh_handler, register_khachhang_commands, register_product_commands, register_chat_logger, register_production_commands, register_bang_gia_commands, register_note_commands, register_quy_commands]:
        fn(client)
    register_saved_messages(client)
