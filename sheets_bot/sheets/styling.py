"""StyleMixin — cell number formats and odd-STT row shading (idempotent)."""

from __future__ import annotations

from ..parse import HEADERS, column_letter


class StyleMixin:
    async def ensure_number_formatting(self, sheet_id):
        if sheet_id is None or sheet_id in self._number_formatted:
            return
        self._number_formatted.add(sheet_id)
        num = lambda pattern: {"type": "NUMBER", "pattern": pattern}
        await self._exec(
            self._ss().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": [
                    {"repeatCell": {
                        "range": {"sheetId": sheet_id, "startRowIndex": 1,
                                  "startColumnIndex": 7, "endColumnIndex": 13},
                        "cell": {"userEnteredFormat": {"numberFormat": num("0")}},
                        "fields": "userEnteredFormat.numberFormat"}},
                    {"repeatCell": {
                        "range": {"sheetId": sheet_id, "startRowIndex": 1,
                                  "startColumnIndex": 20, "endColumnIndex": 21},
                        "cell": {"userEnteredFormat": {"numberFormat": num("0.00")}},
                        "fields": "userEnteredFormat.numberFormat"}},
                ]},
            )
        )

    async def ensure_odd_stt_formatting(self, sheet_id):
        if sheet_id is None or sheet_id in self._odd_formatted or "STT" not in HEADERS:
            return
        stt_col = column_letter(HEADERS.index("STT"))
        self._odd_formatted.add(sheet_id)
        await self._exec(
            self._ss().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": [{"addConditionalFormatRule": {
                    "index": 0,
                    "rule": {
                        "ranges": [{"sheetId": sheet_id, "startRowIndex": 1,
                                    "startColumnIndex": 0, "endColumnIndex": len(HEADERS)}],
                        "booleanRule": {
                            "condition": {"type": "CUSTOM_FORMULA",
                                          "values": [{"userEnteredValue": f"=ISODD(N(${stt_col}2))"}]},
                            "format": {"backgroundColor": {"red": 0.92, "green": 0.92, "blue": 0.92}},
                        },
                    },
                }}]},
            )
        )
