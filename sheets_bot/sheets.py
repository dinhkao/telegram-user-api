"""sheets_bot.sheets — all Google Sheets operations.

Faithful port of the Sheets side of bot.js. The Google API client
(googleapiclient) is synchronous, so every blocking `.execute()` is run in a
thread via `asyncio.to_thread` to avoid blocking the Telethon event loop.

State (memoization of one-time formatting like bot.js's *Promises Maps) is kept
on a single `SheetsManager` instance created by the bot at start time.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import requests

from . import config
from .parse import (
    ARRAY_FORMULAS,
    HEADERS,
    MANAGED_HEADER_MARKERS,
    NEW_COLUMNS_BEFORE_LINK,
    a1,
    column_letter,
    contains_all_headers,
    end_column_letter,
    format_iso_with_offset,
    format_date_ddmmyyyy,
    get_gviz_cell_value,
    get_sheet_name_from_rows,
    headers_match,
    normalize_header_cell,
    normalize_product_code,
    parse_gviz_response,
)

log = logging.getLogger("sheets_bot.sheets")

END_ROW = 1000000


def bangkok_now():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Bangkok"))


def bangkok_from_datetime(dt):
    from zoneinfo import ZoneInfo

    return dt.astimezone(ZoneInfo("Asia/Bangkok"))


def get_sheet_context() -> dict:
    now = bangkok_now()
    return {
        "sheet_name": format_date_ddmmyyyy(now),
        "timestamp": format_iso_with_offset(now),
    }


def format_timestamp_from_datetime(dt) -> str:
    if not dt:
        return ""
    return format_iso_with_offset(bangkok_from_datetime(dt))


class SheetsManager:
    def __init__(self):
        self.service = config.get_service()
        self.spreadsheet_id = config.spreadsheet_id()
        self.topic_spreadsheet_id = config.topic_spreadsheet_id()
        self.topic_sheet_gid = config.topic_sheet_gid()
        self.allowed_products_gid = config.allowed_products_gid()
        self.allowed_products_cache_ms = config.allowed_products_cache_ms()
        self.import_sheet_gid = config.import_sheet_gid()

        # Memoization state (mirrors bot.js maps/promises)
        self._ensure_locks: dict[str, asyncio.Lock] = {}
        self._ensured: dict[str, Any] = {}
        self._odd_formatted: set = set()
        self._number_formatted: set = set()
        self._topic_sheet_name = None
        self._import_sheet_name = None
        self._allowed_cache = {"at": 0.0, "values": set()}
        self._global_lock = asyncio.Lock()

    # -- low level ---------------------------------------------------------
    async def _exec(self, request):
        return await asyncio.to_thread(request.execute)

    def _ss(self):
        return self.service.spreadsheets()

    # -- header migration --------------------------------------------------
    async def ensure_managed_sheet_header(
        self, sheet_name: str, sheet_id, force_managed: bool = False
    ) -> dict:
        res = await self._exec(
            self._ss().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=a1(sheet_name, f"A1:{end_column_letter()}1"),
            )
        )
        values = res.get("values") or []
        current_header = values[0] if values else []
        normalized = [normalize_header_cell(c) for c in current_header]
        has_headers = any(name != "" for name in normalized)
        is_managed = contains_all_headers(normalized, MANAGED_HEADER_MARKERS)

        if not force_managed and (not has_headers or not is_managed):
            return {"migrated": False, "skipped": True}

        missing_before_link = [n for n in NEW_COLUMNS_BEFORE_LINK if n not in normalized]
        link_idx = normalized.index("Link") if "Link" in normalized else -1
        updated_idx = (
            normalized.index("Cập nhật lần cuối")
            if "Cập nhật lần cuối" in normalized
            else -1
        )

        if (
            has_headers
            and missing_before_link
            and link_idx >= 0
            and updated_idx == link_idx + 1
            and sheet_id is not None
        ):
            await self._exec(
                self._ss().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={
                        "requests": [
                            {
                                "insertDimension": {
                                    "range": {
                                        "sheetId": sheet_id,
                                        "dimension": "COLUMNS",
                                        "startIndex": link_idx,
                                        "endIndex": link_idx + len(missing_before_link),
                                    },
                                    "inheritFromBefore": False,
                                }
                            }
                        ]
                    },
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

    # -- formatting --------------------------------------------------------
    async def ensure_array_formulas(self, sheet_name: str):
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

    async def ensure_number_formatting(self, sheet_id):
        if sheet_id is None or sheet_id in self._number_formatted:
            return
        self._number_formatted.add(sheet_id)
        await self._exec(
            self._ss().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={
                    "requests": [
                        {
                            "repeatCell": {
                                "range": {
                                    "sheetId": sheet_id,
                                    "startRowIndex": 1,
                                    "startColumnIndex": 7,
                                    "endColumnIndex": 13,
                                },
                                "cell": {
                                    "userEnteredFormat": {
                                        "numberFormat": {"type": "NUMBER", "pattern": "0"}
                                    }
                                },
                                "fields": "userEnteredFormat.numberFormat",
                            }
                        },
                        {
                            "repeatCell": {
                                "range": {
                                    "sheetId": sheet_id,
                                    "startRowIndex": 1,
                                    "startColumnIndex": 20,
                                    "endColumnIndex": 21,
                                },
                                "cell": {
                                    "userEnteredFormat": {
                                        "numberFormat": {"type": "NUMBER", "pattern": "0.00"}
                                    }
                                },
                                "fields": "userEnteredFormat.numberFormat",
                            }
                        },
                    ]
                },
            )
        )

    async def ensure_odd_stt_formatting(self, sheet_id):
        if sheet_id is None or sheet_id in self._odd_formatted:
            return
        if "STT" not in HEADERS:
            return
        stt_col_letter = column_letter(HEADERS.index("STT"))
        self._odd_formatted.add(sheet_id)
        await self._exec(
            self._ss().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={
                    "requests": [
                        {
                            "addConditionalFormatRule": {
                                "index": 0,
                                "rule": {
                                    "ranges": [
                                        {
                                            "sheetId": sheet_id,
                                            "startRowIndex": 1,
                                            "startColumnIndex": 0,
                                            "endColumnIndex": len(HEADERS),
                                        }
                                    ],
                                    "booleanRule": {
                                        "condition": {
                                            "type": "CUSTOM_FORMULA",
                                            "values": [
                                                {
                                                    "userEnteredValue": f"=ISODD(N(${stt_col_letter}2))"
                                                }
                                            ],
                                        },
                                        "format": {
                                            "backgroundColor": {
                                                "red": 0.92,
                                                "green": 0.92,
                                                "blue": 0.92,
                                            }
                                        },
                                    },
                                },
                            }
                        }
                    ]
                },
            )
        )

    async def sort_by_stt(self, sheet_id):
        if sheet_id is None or "STT" not in HEADERS:
            return
        stt_col_idx = HEADERS.index("STT")
        await self._exec(
            self._ss().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={
                    "requests": [
                        {
                            "sortRange": {
                                "range": {
                                    "sheetId": sheet_id,
                                    "startRowIndex": 1,
                                    "startColumnIndex": 0,
                                    "endColumnIndex": len(HEADERS),
                                },
                                "sortSpecs": [
                                    {"dimensionIndex": stt_col_idx, "sortOrder": "ASCENDING"}
                                ],
                            }
                        }
                    ]
                },
            )
        )

    async def auto_resize_columns(self, sheet_id):
        if sheet_id is None:
            return
        await self._exec(
            self._ss().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={
                    "requests": [
                        {
                            "autoResizeDimensions": {
                                "dimensions": {
                                    "sheetId": sheet_id,
                                    "dimension": "COLUMNS",
                                    "startIndex": 0,
                                    "endIndex": len(HEADERS),
                                }
                            }
                        }
                    ]
                },
            )
        )

    # -- lookups -----------------------------------------------------------
    async def find_sheet_by_name(self, sheet_name: str):
        meta = await self._exec(self._ss().get(spreadsheetId=self.spreadsheet_id))
        for s in meta.get("sheets") or []:
            props = s.get("properties") or {}
            if props.get("title") == sheet_name:
                return s
        return None

    async def get_sheet_name_by_id(self, sheet_id, target_spreadsheet_id: str):
        meta = await self._exec(self._ss().get(spreadsheetId=target_spreadsheet_id))
        for s in meta.get("sheets") or []:
            props = s.get("properties") or {}
            if props.get("sheetId") == sheet_id:
                return props.get("title")
        return None

    async def get_sheet_values(self, sheet_name: str) -> list:
        res = await self._exec(
            self._ss().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=a1(sheet_name, f"A1:{end_column_letter()}{END_ROW}"),
            )
        )
        return res.get("values") or []

    # -- ensure sheet ------------------------------------------------------
    async def ensure_sheet_exists(self, sheet_name: str):
        async with self._global_lock:
            lock = self._ensure_locks.get(sheet_name)
            if lock is None:
                lock = asyncio.Lock()
                self._ensure_locks[sheet_name] = lock
        async with lock:
            if sheet_name in self._ensured:
                return self._ensured[sheet_name]
            sheet_id = await self._ensure_sheet_exists_inner(sheet_name)
            self._ensured[sheet_name] = sheet_id
            return sheet_id

    async def _ensure_sheet_exists_inner(self, sheet_name: str):
        meta = await self._exec(self._ss().get(spreadsheetId=self.spreadsheet_id))
        sheet = None
        for s in meta.get("sheets") or []:
            props = s.get("properties") or {}
            if props.get("title") == sheet_name:
                sheet = s
                break

        if not sheet:
            add_response = await self._exec(
                self._ss().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={
                        "requests": [
                            {
                                "addSheet": {
                                    "properties": {
                                        "title": sheet_name,
                                        "index": 0,
                                        "gridProperties": {"frozenRowCount": 1},
                                    }
                                }
                            }
                        ]
                    },
                )
            )
            new_sheet_id = (
                add_response.get("replies", [{}])[0]
                .get("addSheet", {})
                .get("properties", {})
                .get("sheetId")
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
            await self.ensure_number_formatting(new_sheet_id)

            if new_sheet_id is not None:
                await self._exec(
                    self._ss().batchUpdate(
                        spreadsheetId=self.spreadsheet_id,
                        body={
                            "requests": [
                                {
                                    "addProtectedRange": {
                                        "protectedRange": {
                                            "range": {
                                                "sheetId": new_sheet_id,
                                                "startColumnIndex": 0,
                                                "endColumnIndex": len(HEADERS),
                                            },
                                            "warningOnly": True,
                                            "description": "Bot-managed range: editing will show a warning.",
                                        }
                                    }
                                }
                            ]
                        },
                    )
                )

            await self.ensure_odd_stt_formatting(new_sheet_id)
            return new_sheet_id

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
                    body={
                        "requests": [
                            {
                                "updateSheetProperties": {
                                    "properties": {
                                        "sheetId": sheet_id,
                                        "gridProperties": {"frozenRowCount": 1},
                                    },
                                    "fields": "gridProperties.frozenRowCount",
                                }
                            }
                        ]
                    },
                )
            )

        await self.ensure_odd_stt_formatting(sheet_id)
        return sheet_id

    async def migrate_existing_managed_sheets(self):
        meta = await self._exec(self._ss().get(spreadsheetId=self.spreadsheet_id))
        for sheet in meta.get("sheets") or []:
            props = sheet.get("properties") or {}
            sheet_name = props.get("title")
            sheet_id = props.get("sheetId")
            if not sheet_name or sheet_id is None:
                continue
            try:
                status = await self.ensure_managed_sheet_header(sheet_name, sheet_id, False)
                if status and status.get("skipped"):
                    continue
                await self.ensure_array_formulas(sheet_name)
                await self.ensure_number_formatting(sheet_id)
            except Exception as err:  # noqa: BLE001
                log.warning('Header migration skipped for sheet "%s": %s', sheet_name, err)

    # -- topic row helpers -------------------------------------------------
    async def find_topic_rows(self, sheet_name: str, thread_url: str) -> list:
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

    async def clear_rows(self, sheet_name: str, row_numbers: list):
        if not row_numbers:
            return
        blank = [""] * len(HEADERS)
        await self._exec(
            self._ss().values().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={
                    "valueInputOption": "USER_ENTERED",
                    "data": [
                        {
                            "range": a1(sheet_name, f"A{n}:{end_column_letter()}{n}"),
                            "values": [blank],
                        }
                        for n in row_numbers
                    ],
                },
            )
        )

    # -- writes ------------------------------------------------------------
    async def append_timestamp(self, thread_url: str = ""):
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

    async def append_rows(self, rows: list, thread_url: str = "") -> dict | None:
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
            await self.auto_resize_columns(sheet_id)
            await self.sort_by_stt(sheet_id)
            return {"replaced": True, "count": len(rows_with_ts)}

        await self._exec(
            self._ss().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=a1(sheet_name, "A:A"),
                valueInputOption="USER_ENTERED",
                body={"values": rows_with_ts},
            )
        )
        await self.auto_resize_columns(sheet_id)
        await self.sort_by_stt(sheet_id)
        return {"replaced": False, "count": len(rows_with_ts)}

    # -- gviz / cross-sheet lookups ---------------------------------------
    async def _gviz_query(self, spreadsheet_id: str, gid, query: str) -> str:
        access_token = await asyncio.to_thread(config.get_access_token)
        if not access_token:
            raise RuntimeError("Missing access token for GViz query.")
        from urllib.parse import quote

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

    async def get_allowed_product_codes(self) -> set:
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

    async def is_allowed_product_code(self, code: str) -> bool:
        if not code:
            return False
        allowed = await self.get_allowed_product_codes()
        return code in allowed

    async def topic_row_exists(self, thread_id: str) -> bool:
        if not thread_id:
            return False
        escaped = thread_id.replace("'", "\\'")
        query = f"select A where A = '{escaped}'"
        try:
            numeric = int(thread_id)
            query = f"select A where A = {numeric} or A = '{escaped}'"
        except (ValueError, TypeError):
            pass
        body = await self._gviz_query(self.topic_spreadsheet_id, self.topic_sheet_gid, query)
        payload = parse_gviz_response(body)
        rows = (payload.get("table") or {}).get("rows") or []
        return len(rows) > 0

    async def lookup_production_by_thread_id(self, thread_id: str):
        if not thread_id:
            return None
        body = await self._gviz_query(
            self.topic_spreadsheet_id, self.topic_sheet_gid, "select A, B"
        )
        payload = parse_gviz_response(body)
        rows = (payload.get("table") or {}).get("rows") or []
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

    async def lookup_import_row_by_message_id(self, message_id: str):
        if not message_id:
            return None
        escaped = message_id.replace("'", "\\'")
        query = f"select A, B, C, D, E, F, G, H where A = '{escaped}'"
        try:
            numeric = int(message_id)
            query = f"select A, B, C, D, E, F, G, H where A = {numeric} or A = '{escaped}'"
        except (ValueError, TypeError):
            pass
        body = await self._gviz_query(
            self.topic_spreadsheet_id, self.import_sheet_gid, query
        )
        payload = parse_gviz_response(body)
        rows = (payload.get("table") or {}).get("rows") or []
        row = rows[0] if rows else None
        if not row or not row.get("c"):
            return None
        values = []
        for cell in row["c"]:
            value = get_gviz_cell_value(cell)
            values.append("" if value is None else str(value))
        return values

    async def get_import_sheet_name(self):
        if self._import_sheet_name is None:
            self._import_sheet_name = await self.get_sheet_name_by_id(
                self.import_sheet_gid, self.topic_spreadsheet_id
            )
        return self._import_sheet_name

    async def get_topic_sheet_name(self):
        if self._topic_sheet_name is None:
            self._topic_sheet_name = await self.get_sheet_name_by_id(
                self.topic_sheet_gid, self.topic_spreadsheet_id
            )
        return self._topic_sheet_name

    async def append_import_row(self, msg: dict, amount_payload: dict, production_info: dict):
        from .parse import build_hyperlink_formula, build_sheet_row_url

        sheet_name = await self.get_import_sheet_name()
        if not sheet_name:
            raise RuntimeError("Import sheet not found.")

        created_at = format_timestamp_from_datetime(msg.get("date"))
        sender_name = msg.get("sender_name", "")
        message_id = str(msg.get("message_id") or "")
        thread_id = str(msg.get("message_thread_id") or "") if msg.get("message_thread_id") else ""
        note = amount_payload["note"]
        product_code = (production_info or {}).get("productCode") or ""
        row_number = (production_info or {}).get("rowNumber")
        if row_number:
            production_cell = build_hyperlink_formula(
                build_sheet_row_url(self.topic_spreadsheet_id, self.topic_sheet_gid, row_number),
                thread_id,
            )
        else:
            production_cell = thread_id
        message_deep_link = msg.get("message_deep_link", "")
        row_values = [
            [
                message_id,
                created_at,
                sender_name,
                product_code,
                amount_payload["amount"],
                production_cell,
                note,
                message_deep_link,
            ]
        ]

        await self._exec(
            self._ss().batchUpdate(
                spreadsheetId=self.topic_spreadsheet_id,
                body={
                    "requests": [
                        {
                            "insertDimension": {
                                "range": {
                                    "sheetId": self.import_sheet_gid,
                                    "dimension": "ROWS",
                                    "startIndex": 1,
                                    "endIndex": 2,
                                },
                                "inheritFromBefore": False,
                            }
                        }
                    ]
                },
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

    async def append_topic_row(self, msg: dict, thread_url: str, product_code: str):
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

        created_at = format_timestamp_from_datetime(msg.get("date"))
        sender_name = msg.get("sender_name", "")
        row_values = [[thread_id, product_code, created_at, sender_name, thread_url]]

        await self._exec(
            self._ss().batchUpdate(
                spreadsheetId=self.topic_spreadsheet_id,
                body={
                    "requests": [
                        {
                            "insertDimension": {
                                "range": {
                                    "sheetId": self.topic_sheet_gid,
                                    "dimension": "ROWS",
                                    "startIndex": 1,
                                    "endIndex": 2,
                                },
                                "inheritFromBefore": False,
                            }
                        }
                    ]
                },
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
