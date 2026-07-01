"""TopicRowMixin — append a topic/thread registration row (deduped)."""

from __future__ import annotations

from ..clock import format_timestamp_from_datetime
from ..parse import a1


class TopicRowMixin:
    async def get_topic_sheet_name(self):
        if self._topic_sheet_name is None:
            self._topic_sheet_name = await self.get_sheet_name_by_id(
                self.topic_sheet_gid, self.topic_spreadsheet_id
            )
        return self._topic_sheet_name

    async def append_topic_row(self, msg, thread_url, product_code):
        if not thread_url:
            return {"skipped": "missing_thread_url"}
        if not msg.get("message_thread_id"):
            return {"skipped": "missing_thread_id"}

        sheet_name = await self.get_topic_sheet_name()
        if not sheet_name:
            raise RuntimeError("Topic sheet not found.")

        thread_id = str(msg["message_thread_id"])
        if await self.topic_row_exists(thread_id):
            return {"skipped": "duplicate"}

        row_values = [[
            thread_id,
            product_code,
            format_timestamp_from_datetime(msg.get("date")),
            msg.get("sender_name", ""),
            thread_url,
        ]]

        await self._exec(
            self._ss().batchUpdate(
                spreadsheetId=self.topic_spreadsheet_id,
                body={"requests": [{"insertDimension": {
                    "range": {"sheetId": self.topic_sheet_gid, "dimension": "ROWS",
                              "startIndex": 1, "endIndex": 2},
                    "inheritFromBefore": False}}]},
            )
        )
        await self._exec(
            self._ss().values().update(
                spreadsheetId=self.topic_spreadsheet_id,
                range=a1(sheet_name, "A2:E2"),
                valueInputOption="USER_ENTERED",
                body={"values": row_values},
            )
        )
        return {"ok": True}
