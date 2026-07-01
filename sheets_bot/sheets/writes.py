"""WriteMixin — append timestamp rows and append/replace daily data rows."""

from __future__ import annotations

import asyncio
import logging

from ..clock import get_sheet_context
from ..parse import HEADERS, a1, get_sheet_name_from_rows

log = logging.getLogger("sheets_bot.sheets")


class WriteMixin:
    async def append_timestamp(self, thread_url=""):
        ctx = get_sheet_context()
        sheet_name = ctx["sheet_name"]
        sheet_id = await self.ensure_sheet_exists(sheet_name)
        row = [""] * len(HEADERS)
        row[-2] = thread_url or ""
        row[-1] = ctx["timestamp"]
        await self._exec(
            self._ss().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=a1(sheet_name, "A:A"),
                valueInputOption="USER_ENTERED",
                body={"values": [row]},
            )
        )
        await self.auto_resize_columns(sheet_id)

    async def append_rows(self, rows, thread_url=""):
        if not rows:
            return None
        ctx = get_sheet_context()
        sheet_name = get_sheet_name_from_rows(rows) or ctx["sheet_name"]
        sheet_id = await self.ensure_sheet_exists(sheet_name)

        max_data_cols = len(HEADERS) - 2
        rows_with_ts = []
        for row in rows:
            cells = list(row[:max_data_cols])
            while len(cells) < max_data_cols:
                cells.append("")
            cells.append(thread_url or "")
            cells.append(ctx["timestamp"])
            rows_with_ts.append(cells)

        existing = await self.find_topic_rows(sheet_name, thread_url)
        if existing:
            await self.clear_rows(sheet_name, existing)
        await self._exec(
            self._ss().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=a1(sheet_name, "A:A"),
                valueInputOption="USER_ENTERED",
                body={"values": rows_with_ts},
            )
        )
        # Data is in the sheet now — the caller can reply immediately. The
        # cosmetic resize + sort are two more serialized round-trips, so run
        # them in the background instead of blocking the reply.
        async def _finalize():
            try:
                await self.auto_resize_columns(sheet_id)
                await self.sort_by_stt(sheet_id)
            except Exception as err:  # noqa: BLE001
                log.warning("append_rows finalize (resize/sort) failed: %s", err)

        asyncio.create_task(_finalize())
        return {"replaced": bool(existing), "count": len(rows_with_ts)}
