"""LayoutMixin — array formulas, STT sorting, and column auto-resize."""

from __future__ import annotations

from ..parse import ARRAY_FORMULAS, HEADERS, a1


class LayoutMixin:
    async def ensure_array_formulas(self, sheet_name):
        if not ARRAY_FORMULAS:
            return
        await self._exec(
            self._ss().values().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={
                    "valueInputOption": "USER_ENTERED",
                    "data": [
                        {"range": a1(sheet_name, f["range"]), "values": [[f["formula"]]]}
                        for f in ARRAY_FORMULAS
                    ],
                },
            )
        )

    async def sort_by_stt(self, sheet_id):
        if sheet_id is None or "STT" not in HEADERS:
            return
        stt_idx = HEADERS.index("STT")
        await self._exec(
            self._ss().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": [{"sortRange": {
                    "range": {"sheetId": sheet_id, "startRowIndex": 1,
                              "startColumnIndex": 0, "endColumnIndex": len(HEADERS)},
                    "sortSpecs": [{"dimensionIndex": stt_idx, "sortOrder": "ASCENDING"}],
                }}]},
            )
        )

    async def auto_resize_columns(self, sheet_id):
        if sheet_id is None:
            return
        await self._exec(
            self._ss().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": [{"autoResizeDimensions": {"dimensions": {
                    "sheetId": sheet_id, "dimension": "COLUMNS",
                    "startIndex": 0, "endIndex": len(HEADERS)}}}]},
            )
        )
