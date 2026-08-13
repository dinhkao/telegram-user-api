"""Build id của webapp đang được phục vụ = TÊN FILE bundle JS trong webapp/dist.

Vì sao cần: APK giữ WebView sống rất dai (foreground service + wake lock), máy để
nhiều ngày rồi mở lại vẫn chạy đúng bundle đã nạp từ lần khởi động trước — trong
khi server đã deploy bản mới. Không có cách nào để máy đó tự biết mình đang cũ:
`/api/app/reload` chỉ tới được máy ĐANG kết nối đúng lúc admin bấm.

Cách chốt: /ws gửi {"type":"hello","build":"index-XXXX.js"} ngay khi kết nối
(websocket_routes). Client so với tên file của CHÍNH nó (import.meta.url trong
webapp/src/realtime.ts) — khác nhau = đang chạy bản cũ → tự tải lại. Mọi lần
resume đều nối lại socket nên kiểm tra này chạy đúng lúc cần.

Cache theo (mtime, size) của index.html → build lại là đổi ngay, KHÔNG cần
restart server; đọc file chỉ 1 lần cho mỗi lần deploy chứ không mỗi lần kết nối.
"""
from __future__ import annotations

import os
import re

_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "webapp", "dist")
_INDEX = os.path.join(_DIST, "index.html")

# <script type="module" src="./assets/index-sqyUf3YA.js">
_RE = re.compile(r"assets/(index-[A-Za-z0-9_-]+\.js)")

_cached: tuple[tuple[int, int], str] | None = None


def build_id() -> str:
    """Tên file bundle JS hiện hành ("index-sqyUf3YA.js"); "" nếu chưa build/không đọc được.

    Rỗng = client bỏ qua, không tải lại — thà không kiểm tra còn hơn ép reload nhầm.
    """
    global _cached
    try:
        st = os.stat(_INDEX)
    except OSError:
        return ""
    key = (st.st_mtime_ns, st.st_size)
    if _cached and _cached[0] == key:
        return _cached[1]
    try:
        with open(_INDEX, "r", encoding="utf-8") as f:
            m = _RE.search(f.read())
    except OSError:
        return ""
    bid = m.group(1) if m else ""
    _cached = (key, bid)
    return bid
