from __future__ import annotations

import asyncio
import random
import re
import time


async def queue_html_for_print(ref, html: str, copies: int = 1, settle_ms: float = 0.12, gap_ms: float = 0.22) -> bool:
    if ref is None:
        return False
    copies = max(1, copies)
    batch_id = f"{int(time.time() * 1000)}-{random.randint(100000, 999999)}"
    for i in range(copies):
        marker_tag = f"<!-- print-queue:{batch_id}:copy:{i + 1}/{copies} -->"
        match = re.search(r"</body>", html, re.IGNORECASE)
        html_with_marker = html[:match.start()] + marker_tag + "\n" + html[match.start():] if match else html + "\n" + marker_tag
        ref.set(html_with_marker)
        if settle_ms > 0:
            await asyncio.sleep(settle_ms)
        ref.delete()
        if i < copies - 1 and gap_ms > 0:
            await asyncio.sleep(gap_ms)
    return True
