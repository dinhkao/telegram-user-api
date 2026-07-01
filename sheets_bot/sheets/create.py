"""CreateMixin — create a new managed daily sheet or bring an existing one up
to spec (headers, formulas, number formats, freeze, protected range, shading)."""

from __future__ import annotations

from ..parse import HEADERS, a1, end_column_letter


class CreateMixin:
    async def _create_managed_sheet(self, sheet_name):
        add = await self._exec(
            self._ss().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {
                    "title": sheet_name, "index": 0,
                    "gridProperties": {"frozenRowCount": 1}}}}]},
            )
        )
        new_id = (
            add.get("replies", [{}])[0].get("addSheet", {}).get("properties", {}).get("sheetId")
        )
        await self._exec(
            self._ss().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=a1(sheet_name, f"A1:{end_column_letter()}1"),
                valueInputOption="USER_ENTERED",
                body={"values": [HEADERS]},
            )
        )
        await self.ensure_array_formulas(sheet_name)
        await self.ensure_number_formatting(new_id)
        if new_id is not None:
            await self._exec(
                self._ss().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={"requests": [{"addProtectedRange": {"protectedRange": {
                        "range": {"sheetId": new_id, "startColumnIndex": 0,
                                  "endColumnIndex": len(HEADERS)},
                        "warningOnly": True,
                        "description": "Bot-managed range: editing will show a warning."}}}]},
                )
            )
        await self.ensure_odd_stt_formatting(new_id)
        return new_id

    async def _update_existing_sheet(self, sheet, sheet_name):
        props = sheet.get("properties") or {}
        sheet_id = props.get("sheetId")
        await self.ensure_managed_sheet_header(sheet_name, sheet_id, True)
        await self.ensure_array_formulas(sheet_name)
        await self.ensure_number_formatting(sheet_id)
        frozen = ((props.get("gridProperties") or {}).get("frozenRowCount")) or 0
        if frozen < 1:
            await self._exec(
                self._ss().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={"requests": [{"updateSheetProperties": {
                        "properties": {"sheetId": sheet_id,
                                       "gridProperties": {"frozenRowCount": 1}},
                        "fields": "gridProperties.frozenRowCount"}}]},
                )
            )
        await self.ensure_odd_stt_formatting(sheet_id)
        return sheet_id
