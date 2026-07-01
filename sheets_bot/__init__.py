"""sheets_bot — Google Sheets writer Telegram bot.

Ported from the standalone Node.js bot `bot-nhap-phieu-sp` (bot.js) into the
Telethon app. Public entrypoint: `sheets_bot.bot.start_sheets_bot`.
"""

from .bot import start_sheets_bot

__all__ = ["start_sheets_bot"]
