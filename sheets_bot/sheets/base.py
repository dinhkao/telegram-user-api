"""SheetsBase — shared state, service handle, and low-level exec wrapper."""

from __future__ import annotations

import asyncio

from .. import config

END_ROW = 1000000


class SheetsBase:
    def __init__(self):
        self.service = config.get_service()
        self.spreadsheet_id = config.spreadsheet_id()
        self.topic_spreadsheet_id = config.topic_spreadsheet_id()
        self.topic_sheet_gid = config.topic_sheet_gid()
        self.allowed_products_gid = config.allowed_products_gid()
        self.allowed_products_cache_ms = config.allowed_products_cache_ms()
        self.import_sheet_gid = config.import_sheet_gid()

        # Memoization state (mirrors bot.js maps/promises).
        self._ensure_locks: dict[str, asyncio.Lock] = {}
        self._ensured: dict = {}
        self._odd_formatted: set = set()
        self._number_formatted: set = set()
        self._topic_sheet_name = None
        self._import_sheet_name = None
        self._allowed_cache = {"at": 0.0, "values": set()}
        self._global_lock = asyncio.Lock()

    async def _exec(self, request):
        return await asyncio.to_thread(request.execute)

    def _ss(self):
        return self.service.spreadsheets()
