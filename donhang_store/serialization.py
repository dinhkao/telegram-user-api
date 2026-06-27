from __future__ import annotations
import time

from vn import vn_normalize


def _row_args(msg: dict) -> tuple:
    text, raw = msg.get("text") or "", msg.get("raw_text") or ""
    return (msg["id"], msg.get("date"), text, raw, vn_normalize(text + " " + raw), msg.get("media"), msg.get("reply_to"), time.time())
