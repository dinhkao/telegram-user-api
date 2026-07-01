"""SheetsBase — shared state, service handle, and low-level exec wrapper."""

from __future__ import annotations

import asyncio
import threading

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
        # googleapiclient's default httplib2 transport is NOT thread-safe: the
        # service (one TLS socket) is shared across every to_thread execute().
        # Concurrent requests corrupt the connection (SSL RECORD_LAYER_FAILURE).
        # Serialize execute() so only one HTTP call touches the socket at a time.
        self._http_lock = threading.Lock()

    async def _exec(self, request):
        def _run():
            with self._http_lock:
                return request.execute()

        return await asyncio.to_thread(_run)

    def _ss(self):
        return self.service.spreadsheets()
