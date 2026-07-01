from __future__ import annotations

import logging
import os

from aiohttp import web
from telethon import TelegramClient

from audit_log import init_audit_db
from firebase_html_to_png import start_listener as start_html_to_png
from telegram_gateway import TelegramGateway

from server_app.app_factory import create_app
from server_app.command_bootstrap import register_command_handlers
from server_app.config import API_HASH, API_ID, PHONE, PORT, SESSION
from server_app.donhang_bootstrap import bootstrap_donhang, init_donhang_db, register_donhang_live
from server_app.saved_messages import load_recent_messages
from server_app.state import set_client, set_donhang_db, set_gateway, set_duy_user_id
from server_app.tasks import spawn_tracked

log = logging.getLogger("server")


async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    set_client(client)
    await client.start(phone=PHONE)
    gateway = TelegramGateway(client)
    set_gateway(gateway)
    gateway.install()
    init_audit_db()
    me = await client.get_me()
    set_duy_user_id(me.id)
    log.info("Logged in as %s (id=%d)", me.first_name, me.id)
    log.info("Listening to Saved Messages...")
    await load_recent_messages(client, limit=100)
    register_command_handlers(client)
    start_html_to_png(client)
    db = init_donhang_db()
    set_donhang_db(db)
    register_donhang_live(client, db)
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT, reuse_address=True, reuse_port=True).start()
    log.info("Web server: http://localhost:%d", PORT)
    spawn_tracked("donhang.bootstrap", bootstrap_donhang(client, db))

    # Start bot client (merged from bot-don-hang)
    from server_app.bot_bootstrap import start_bot
    spawn_tracked("bot.startup", start_bot(API_ID, API_HASH))

    # Start Google Sheets handlers (ported from bot-nhap-phieu-sp).
    # Runs on the user-account client — no bot token. TẮT mặc định (không dùng nữa);
    # bật lại: SHEETS_BOT_ENABLED=true. No-op unless Google creds set.
    if os.getenv("SHEETS_BOT_ENABLED", "").strip().lower() in ("1", "true", "yes"):
        from sheets_bot import start_sheets_bot
        spawn_tracked("sheets_bot.startup", start_sheets_bot(client))
    else:
        log.info("sheets_bot disabled (set SHEETS_BOT_ENABLED=true to enable)")

    await client.run_until_disconnected()
