from __future__ import annotations

import json

from vn import vn_normalize


def generate_customer_html(conn) -> str:
    rows = conn.execute("SELECT firebase_key, json FROM customers WHERE deleted_at IS NULL ORDER BY json_extract(json, '$.name') COLLATE NOCASE").fetchall()
    items = []
    for row in rows:
        cust = json.loads(row["json"])
        name = cust.get("name", "N/A")
        fb_key = row["firebase_key"]
        kv_id = cust.get("kh_id") or cust.get("kiotvietID") or ""
        note = cust.get("note") or cust.get("ghi_chu") or ""
        extra = f" | KiotViet ID: {kv_id}" if kv_id else ""
        extra += f" | Ghi chú: {note}" if note else ""
        items.append(f'<div class="customer-item" data-name="{vn_normalize(name)}"><b>{name}</b> | ID: {fb_key}{extra}<button onclick="copyCommand(\'{fb_key}\', this)">Sao chép lệnh</button></div>')
    total = len(items)
    return "<!DOCTYPE html><html lang='vi'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1.0'><title>Tìm kiếm khách hàng</title><style>body{font-family:Segoe UI,Tahoma,sans-serif;max-width:1200px;margin:0 auto;padding:20px;background:#f5f5f5}.container{background:#fff;border-radius:10px;padding:30px;box-shadow:0 2px 10px rgba(0,0,0,.1)}.search-box{width:100%;padding:15px;font-size:16px;border:2px solid #ddd;border-radius:8px;margin-bottom:20px;box-sizing:border-box}.customer-list{max-height:600px;overflow-y:auto;border:1px solid #ddd;border-radius:8px}.customer-item{padding:15px;border-bottom:1px solid #eee;display:flex;justify-content:space-between;align-items:center}.copy-button{background:#4CAF50;color:#fff;border:none;padding:8px 15px;border-radius:5px;cursor:pointer}</style></head><body><div class='container'><h1>Tìm kiếm khách hàng</h1><div class='stats'>Tổng số khách hàng: <strong id='total-customers'>" + str(total) + "</strong> | Hiển thị: <strong id='showing-customers'>" + str(total) + "</strong></div><input type='text' class='search-box' id='searchBox' placeholder='Nhập tên khách hàng để tìm kiếm...' autofocus><div class='customer-list' id='customerList'>" + "".join(items) + "</div></div><script>function copyCommand(id,btn){navigator.clipboard.writeText(id).then(()=>{btn.textContent='Đã copy!';setTimeout(()=>btn.textContent='Sao chép lệnh',1500)}).catch(()=>{const ta=document.createElement('textarea');ta.value=id;document.body.appendChild(ta);ta.select();document.execCommand('copy');document.body.removeChild(ta);btn.textContent='Đã copy!';setTimeout(()=>btn.textContent='Sao chép lệnh',1500)})}document.getElementById('searchBox').addEventListener('input',function(e){const q=e.target.value.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');let count=0;document.querySelectorAll('.customer-item').forEach(item=>{const name=(item.getAttribute('data-name')||'').toLowerCase();item.style.display=!q||name.includes(q)?'':'none';if(!q||name.includes(q))count++;});document.getElementById('showing-customers').textContent=count;});</script></body></html>"


def fmt_task_list(tasks: list[dict]) -> str:
    lines = [f"<b>📋 Danh sách task ({len(tasks)}):</b>", ""]
    for t in tasks:
        ts = t["task_status"]
        done = [k for k, v in ts.items() if isinstance(v, dict) and (v.get("done") or v.get("skip"))]
        pending = [k for k, v in ts.items() if isinstance(v, dict) and not (v.get("done") or v.get("skip"))]
        parts = [f"• <b>{t.get('name') or t['firebase_key']}</b> ({'V2' if t.get('flow_version') == 2 else 'V1'})"]
        if done:
            parts.append(f"✅ {', '.join(done)}")
        if pending:
            parts.append(f"⏳ {', '.join(pending)}")
        lines.append(" ".join(parts))
    return "\n".join(lines)

