from __future__ import annotations


def format_search_results(results: list[dict]) -> str:
    """Format customer search results as HTML message text.
    Each line: `• <b>{name}</b> — <code>add khach hang {firebase_key}</code> | KV: ... | note`."""
    lines = [f"🔍 <b>Tìm thấy {len(results)} khách hàng:</b>", ""]
    for c in results:
        name = c.get("name", "N/A")
        firebase_key = c.get("_firebase_key") or name.lower().replace(" ", "_")
        kv_id = c.get("kh_id") or c.get("kiotvietID") or ""
        note = c.get("note") or c.get("ghi_chu") or ""
        extra = f" | KV: {kv_id}" if kv_id else ""
        extra += f" | {note}" if note else ""
        lines.append(f"• <b>{name}</b> — <code>add khach hang {firebase_key}</code>{extra}")
    return "\n".join(lines)


def format_not_found(query: str) -> str:
    return f"❌ Không tìm thấy khách hàng nào tên '{query}'"