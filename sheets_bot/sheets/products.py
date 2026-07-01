"""ProductMixin — cached allowed-product-code set from the topic spreadsheet."""

from __future__ import annotations

import time

from ..parse import a1, normalize_product_code


class ProductMixin:
    async def get_allowed_product_codes(self):
        now = time.time() * 1000
        cache = self._allowed_cache
        if cache["values"] and now - cache["at"] < self.allowed_products_cache_ms:
            return cache["values"]

        sheet_name = await self.get_sheet_name_by_id(
            self.allowed_products_gid, self.topic_spreadsheet_id
        )
        if not sheet_name:
            raise RuntimeError("Allowed products sheet not found.")

        res = await self._exec(
            self._ss().values().get(
                spreadsheetId=self.topic_spreadsheet_id, range=a1(sheet_name, "A:A")
            )
        )
        codes = set()
        for row in res.get("values") or []:
            if not row:
                continue
            code = normalize_product_code(row[0])
            if code:
                codes.add(code)
        self._allowed_cache = {"at": now, "values": codes}
        return codes

    async def is_allowed_product_code(self, code):
        if not code:
            return False
        return code in await self.get_allowed_product_codes()
