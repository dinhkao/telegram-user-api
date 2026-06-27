"""One-off message fetcher for Telegram chats."""
from api_helpers.fetch_core import main, parse_args, sender_name


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

