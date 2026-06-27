from __future__ import annotations

import os

from aiohttp import web

_API_KEY = os.getenv("TG_EDIT_API_KEY", "")


def check_auth(request: web.Request) -> bool:
    return not _API_KEY or request.headers.get("X-API-Key") == _API_KEY

