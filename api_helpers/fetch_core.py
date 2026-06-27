from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from telethon import TelegramClient

from utils.logger import configure_logging

load_dotenv()
configure_logging()
log = logging.getLogger("fetch")

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
PHONE = os.getenv("PHONE", "")
TARGET_CHAT = os.getenv("TARGET_CHAT", "")


def sender_name(sender):
    if not sender:
        return "Unknown"
    if hasattr(sender, "title"):
        name = sender.title
        if getattr(sender, "username", None):
            name += f" (@{sender.username})"
        return name
    name = f"{sender.first_name or ''} {sender.last_name or ''}".strip()
    if getattr(sender, "username", None):
        name += f" (@{sender.username})"
    return name


def parse_args():
    args = {"limit": 5, "chat": TARGET_CHAT, "since": None, "before": None}
    positional = []
    i = 1
    while i < len(sys.argv):
        a = sys.argv[i]
        if a.startswith("--"):
            key = a[2:]
            if key in ("since", "before") and i + 1 < len(sys.argv):
                i += 1
                args[key] = datetime.fromisoformat(sys.argv[i]).replace(tzinfo=timezone.utc)
        else:
            positional.append(a)
        i += 1
    if positional:
        args["limit"] = int(positional[0])
    if len(positional) > 1:
        args["chat"] = positional[1]
    return args


async def main():
    args = parse_args()
    client = TelegramClient("user_session", API_ID, API_HASH)
    await client.start(phone=PHONE)
    entity = await client.get_entity(args["chat"])
    name = entity.title if hasattr(entity, "title") else entity.first_name
    log.info("Chat: %s (ID: %s)", name, entity.id)
    log.info("Last %d messages", args["limit"])
    kwargs = {"limit": args["limit"]}
    if args["since"]:
        kwargs["offset_date"] = args["since"]
        log.info("  Since: %s UTC", args["since"].strftime("%Y-%m-%d %H:%M:%S"))
    if args["before"]:
        kwargs["offset_date"] = args["before"]
        log.info("  Before: %s UTC", args["before"].strftime("%Y-%m-%d %H:%M:%S"))
    log.debug("Fetching with kwargs=%s", kwargs)
    messages = await client.get_messages(entity, **kwargs)
    for i, msg in enumerate(messages, 1):
        s = await msg.get_sender()
        log.info("[%d] ID:%d | %s | %s", i, msg.id, msg.date.strftime("%Y-%m-%d %H:%M:%S"), sender_name(s))
        if msg.text:
            log.info("    %s", msg.text)
        if msg.media:
            log.debug("    [Media: %s]", type(msg.media).__name__.replace("MessageMedia", ""))
        if msg.reply_to_msg_id:
            log.debug("    [Reply to: %s]", msg.reply_to_msg_id)
    log.info("Done — %d messages fetched.", len(messages))
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

