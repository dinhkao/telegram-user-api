"""GvizMixin — gviz REST queries and cross-sheet lookups by id."""

from __future__ import annotations

import asyncio
from urllib.parse import quote

import requests

from .. import config
from ..parse import get_gviz_cell_value, parse_gviz_response


class GvizMixin:
    async def _gviz_query(self, spreadsheet_id, gid, query):
        access_token = await asyncio.to_thread(config.get_access_token)
        if not access_token:
            raise RuntimeError("Missing access token for GViz query.")
        url = (
            f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq"
            f"?tqx=out:json&gid={gid}&tq={quote(query)}&access_token={access_token}"
        )

        def _do():
            resp = requests.get(url, timeout=30)
            if resp.status_code >= 400:
                raise RuntimeError(f"GViz request failed: {resp.status_code}")
            return resp.text

        return await asyncio.to_thread(_do)

    async def topic_row_exists(self, thread_id):
        if not thread_id:
            return False
        escaped = thread_id.replace("'", "\\'")
        query = f"select A where A = '{escaped}'"
        try:
            query = f"select A where A = {int(thread_id)} or A = '{escaped}'"
        except (ValueError, TypeError):
            pass
        body = await self._gviz_query(self.topic_spreadsheet_id, self.topic_sheet_gid, query)
        rows = (parse_gviz_response(body).get("table") or {}).get("rows") or []
        return len(rows) > 0

    async def lookup_production_by_thread_id(self, thread_id):
        if not thread_id:
            return None
        body = await self._gviz_query(self.topic_spreadsheet_id, self.topic_sheet_gid, "select A, B")
        rows = (parse_gviz_response(body).get("table") or {}).get("rows") or []
        for i, row in enumerate(rows):
            cells = (row or {}).get("c") or []
            id_value = get_gviz_cell_value(cells[0] if len(cells) > 0 else None)
            if id_value is None:
                continue
            if str(id_value).strip() == thread_id:
                code_value = get_gviz_cell_value(cells[1] if len(cells) > 1 else None)
                product_code = "" if code_value is None else str(code_value).strip()
                return {"productCode": product_code, "rowNumber": i + 2}
        return None

    async def lookup_import_row_by_message_id(self, message_id):
        if not message_id:
            return None
        escaped = message_id.replace("'", "\\'")
        cols = "A, B, C, D, E, F, G, H"
        query = f"select {cols} where A = '{escaped}'"
        try:
            query = f"select {cols} where A = {int(message_id)} or A = '{escaped}'"
        except (ValueError, TypeError):
            pass
        body = await self._gviz_query(self.topic_spreadsheet_id, self.import_sheet_gid, query)
        rows = (parse_gviz_response(body).get("table") or {}).get("rows") or []
        row = rows[0] if rows else None
        if not row or not row.get("c"):
            return None
        return [("" if get_gviz_cell_value(c) is None else str(get_gviz_cell_value(c))) for c in row["c"]]
