"""bot_handlers/sheets_helpers.py — Google Sheets parsing helpers."""
import json
import re


def parse_gviz_response(text):
    match = re.search(r'google\.visualization\.Query\.setResponse\(([\s\S]*?)\);?\s*$', text)
    if not match:
        raise ValueError("Không đọc được dữ liệu Google Sheets.")
    return json.loads(match.group(1))


def find_private_post_anchor(text):
    match = re.search(r'<a\s+href=["\'](tg://privatepost\?[^"\']+)["\'][^>]*>([\s\S]*?)</a>', text)
    if not match:
        return None
    return {"link": match.group(1), "text": match.group(2)}


def parse_order_cell(raw, required_tag=None, excluded_tag=None):
    normalized = str(raw or "").replace('""', '"')
    if not normalized.strip():
        return None
    if required_tag and required_tag not in normalized:
        return None
    if excluded_tag and excluded_tag in normalized:
        return None
    before_block = normalized.split('<blockquote')[0] or ""
    anchor = find_private_post_anchor(before_block)
    if not anchor:
        block_match = re.search(r'<blockquote[^>]*>([\s\S]*?)</blockquote>', normalized, re.I)
        if block_match:
            anchor = find_private_post_anchor(block_match.group(1))
    if not anchor:
        matches = list(re.finditer(r'<a\s+href=["\'](tg://privatepost\?[^"\']+)["\'][^>]*>([\s\S]*?)</a>', normalized))
        if matches:
            anchor = {"link": matches[-1].group(1), "text": matches[-1].group(2)}
    if not anchor:
        return None
    text = re.sub(r'<[^>]*>', '', str(anchor.get("text") or "")).replace(r'\s+', ' ').strip()
    if not text:
        return None
    return {"text": text}


async def fetch_orders_by_tag(sheet_id, sheet_gid, private_channel_id, required_tag=None, excluded_tag=None):
    import aiohttp
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?gid={sheet_gid}&tqx=out:json"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            text = await resp.text()
    data = parse_gviz_response(text)
    rows = (data.get("table") or {}).get("rows", [])
    orders = []
    for row in rows:
        cells = row.get("c", [])
        id_cell = cells[0] if len(cells) > 0 else None
        raw_id = id_cell.get("v") if id_cell else None
        message_id = str(raw_id or "").replace(r"[^0-9]", "").strip()
        cell = cells[1] if len(cells) > 1 else None
        raw = cell.get("v") if cell else None
        if not raw or not message_id:
            continue
        parsed = parse_order_cell(raw, required_tag, excluded_tag)
        if parsed:
            orders.append({
                "text": parsed["text"],
                "link": f"tg://privatepost?channel={private_channel_id}&post={message_id}",
            })
    return orders


def chunk_lines(lines, max_len=3800):
    chunks = []
    current = ""
    for line in lines:
        piece = str(line)
        if not current:
            current = piece
            continue
        candidate = f"{current}\n\n{piece}"
        if len(candidate) > max_len:
            chunks.append(current)
            current = piece
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks
