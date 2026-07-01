"""LookupMixin — read-only sheet/value lookups and row clearing."""

from __future__ import annotations

import logging

from ..parse import HEADERS, a1, end_column_letter
from .base import END_ROW

log = logging.getLogger("sheets_bot.sheets")


class LookupMixin:
    async def find_sheet_by_name(self, sheet_name):
        meta = await self._exec(self._ss().get(spreadsheetId=self.spreadsheet_id))
        for s in meta.get("sheets") or []:
            if (s.get("properties") or {}).get("title") == sheet_name:
                return s
        return None

    async def get_sheet_name_by_id(self, sheet_id, target_spreadsheet_id):
        meta = await self._exec(self._ss().get(spreadsheetId=target_spreadsheet_id))
        for s in meta.get("sheets") or []:
            props = s.get("properties") or {}
            if props.get("sheetId") == sheet_id:
                return props.get("title")
        return None

    async def get_sheet_values(self, sheet_name):
        res = await self._exec(
            self._ss().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=a1(sheet_name, f"A1:{end_column_letter()}{END_ROW}"),
            )
        )
        return res.get("values") or []

    async def find_topic_rows(self, sheet_name, thread_url):
        if not thread_url:
            return []
        try:
            res = await self._exec(
                self._ss().values().get(
                    spreadsheetId=self.spreadsheet_id,
                    range=a1(sheet_name, f"A2:{end_column_letter()}{END_ROW}"),
                )
            )
        except Exception as err:  # noqa: BLE001
            log.warning("find_topic_rows: treating missing range as empty: %s", err)
            return []
        rows = res.get("values") or []
        if "Link" not in HEADERS:
            return []
        link_idx = HEADERS.index("Link")
        matches = []
        for idx, row in enumerate(rows):
            val = row[link_idx] if len(row) > link_idx else ""
            if ("" if val is None else str(val)).strip() == thread_url:
                matches.append(idx + 2)
        return matches

    async def clear_rows(self, sheet_name, row_numbers):
        if not row_numbers:
            return
        blank = [""] * len(HEADERS)
        await self._exec(
            self._ss().values().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"valueInputOption": "USER_ENTERED", "data": [
                    {"range": a1(sheet_name, f"A{n}:{end_column_letter()}{n}"), "values": [blank]}
                    for n in row_numbers
                ]},
            )
        )
