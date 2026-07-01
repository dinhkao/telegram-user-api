"""HeaderMixin — managed-header detection, migration, and startup sweep."""

from __future__ import annotations

import logging

from ..parse import (
    HEADERS,
    MANAGED_HEADER_MARKERS,
    NEW_COLUMNS_BEFORE_LINK,
    a1,
    contains_all_headers,
    end_column_letter,
    headers_match,
    normalize_header_cell,
)

log = logging.getLogger("sheets_bot.sheets")


class HeaderMixin:
    async def ensure_managed_sheet_header(self, sheet_name, sheet_id, force_managed=False) -> dict:
        res = await self._exec(
            self._ss().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=a1(sheet_name, f"A1:{end_column_letter()}1"),
            )
        )
        values = res.get("values") or []
        current = values[0] if values else []
        normalized = [normalize_header_cell(c) for c in current]
        has_headers = any(name != "" for name in normalized)
        is_managed = contains_all_headers(normalized, MANAGED_HEADER_MARKERS)

        if not force_managed and (not has_headers or not is_managed):
            return {"migrated": False, "skipped": True}

        missing = [n for n in NEW_COLUMNS_BEFORE_LINK if n not in normalized]
        link_idx = normalized.index("Link") if "Link" in normalized else -1
        updated_idx = normalized.index("Cập nhật lần cuối") if "Cập nhật lần cuối" in normalized else -1

        if has_headers and missing and link_idx >= 0 and updated_idx == link_idx + 1 and sheet_id is not None:
            await self._exec(
                self._ss().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={"requests": [{"insertDimension": {
                        "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                                  "startIndex": link_idx, "endIndex": link_idx + len(missing)},
                        "inheritFromBefore": False}}]},
                )
            )

        if not has_headers or not headers_match(normalized, HEADERS):
            await self._exec(
                self._ss().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=a1(sheet_name, f"A1:{end_column_letter()}1"),
                    valueInputOption="USER_ENTERED",
                    body={"values": [HEADERS]},
                )
            )
            return {"migrated": True, "skipped": False}
        return {"migrated": False, "skipped": False}

    async def migrate_existing_managed_sheets(self):
        meta = await self._exec(self._ss().get(spreadsheetId=self.spreadsheet_id))
        for sheet in meta.get("sheets") or []:
            props = sheet.get("properties") or {}
            name, sid = props.get("title"), props.get("sheetId")
            if not name or sid is None:
                continue
            try:
                status = await self.ensure_managed_sheet_header(name, sid, False)
                if status and status.get("skipped"):
                    continue
                await self.ensure_array_formulas(name)
                await self.ensure_number_formatting(sid)
            except Exception as err:  # noqa: BLE001
                log.warning('Header migration skipped for sheet "%s": %s', name, err)
