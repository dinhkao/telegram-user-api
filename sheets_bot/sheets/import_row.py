"""ImportRowMixin — append a stock-import row to the topic spreadsheet."""

from __future__ import annotations

from ..clock import format_timestamp_from_datetime
from ..parse import a1, build_hyperlink_formula, build_sheet_row_url


class ImportRowMixin:
    async def get_import_sheet_name(self):
        if self._import_sheet_name is None:
            self._import_sheet_name = await self.get_sheet_name_by_id(
                self.import_sheet_gid, self.topic_spreadsheet_id
            )
        return self._import_sheet_name

    async def append_import_row(self, msg, amount_payload, production_info):
        sheet_name = await self.get_import_sheet_name()
        if not sheet_name:
            raise RuntimeError("Import sheet not found.")

        thread_id = str(msg.get("message_thread_id") or "") if msg.get("message_thread_id") else ""
        row_number = (production_info or {}).get("rowNumber")
        production_cell = (
            build_hyperlink_formula(
                build_sheet_row_url(self.topic_spreadsheet_id, self.topic_sheet_gid, row_number),
                thread_id,
            )
            if row_number
            else thread_id
        )
        row_values = [[
            str(msg.get("message_id") or ""),
            format_timestamp_from_datetime(msg.get("date")),
            msg.get("sender_name", ""),
            (production_info or {}).get("productCode") or "",
            amount_payload["amount"],
            production_cell,
            amount_payload["note"],
            msg.get("message_deep_link", ""),
        ]]

        await self._exec(
            self._ss().batchUpdate(
                spreadsheetId=self.topic_spreadsheet_id,
                body={"requests": [{"insertDimension": {
                    "range": {"sheetId": self.import_sheet_gid, "dimension": "ROWS",
                              "startIndex": 1, "endIndex": 2},
                    "inheritFromBefore": False}}]},
            )
        )
        await self._exec(
            self._ss().values().update(
                spreadsheetId=self.topic_spreadsheet_id,
                range=a1(sheet_name, "A2:H2"),
                valueInputOption="USER_ENTERED",
                body={"values": row_values},
            )
        )
        return {"ok": True}
