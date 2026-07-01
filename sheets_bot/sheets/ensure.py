"""EnsureMixin — idempotent per-sheet ensure with async locking + dispatch."""

from __future__ import annotations

import asyncio


class EnsureMixin:
    async def ensure_sheet_exists(self, sheet_name):
        async with self._global_lock:
            lock = self._ensure_locks.get(sheet_name)
            if lock is None:
                lock = asyncio.Lock()
                self._ensure_locks[sheet_name] = lock
        async with lock:
            if sheet_name in self._ensured:
                return self._ensured[sheet_name]
            sheet_id = await self._ensure_sheet_exists_inner(sheet_name)
            self._ensured[sheet_name] = sheet_id
            return sheet_id

    async def _ensure_sheet_exists_inner(self, sheet_name):
        meta = await self._exec(self._ss().get(spreadsheetId=self.spreadsheet_id))
        for s in meta.get("sheets") or []:
            if (s.get("properties") or {}).get("title") == sheet_name:
                return await self._update_existing_sheet(s, sheet_name)
        return await self._create_managed_sheet(sheet_name)
