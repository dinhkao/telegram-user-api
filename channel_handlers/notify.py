from __future__ import annotations


def build_auto_parse_notification(invoice, assigned_cust, detection) -> list[str]:
    lines = []
    if invoice:
        lines.append(f"🤖 <b>Auto-detect:</b> đã tìm thấy {len(invoice)} sản phẩm\n")
        grand_total = 0
        for item in invoice:
            sp = item.get("sp", "?")
            sl = item.get("sl", 0)
            price = item.get("price", 0)
            sub_total = sl * price
            grand_total += sub_total
            lines.append(f"• <b>{sp}</b> x{sl} @ {price:,}đ = <b>{sub_total:,}đ</b>")
        lines.append(f"\n💰 <b>Tổng cộng: {grand_total:,}đ</b>")
    if assigned_cust:
        if lines:
            lines.append("")
        lines += [f"👤 <b>Đã gán:</b> {assigned_cust['customerName']} ({assigned_cust['score']}%)", f"🎯 Mẫu: \"{assigned_cust['bestMatchedPattern']}\""]
    elif detection.get("matches"):
        if lines:
            lines.append("")
        lines.append("🔍 <b>Khách hàng có thể:</b>")
        for i, m in enumerate(detection["matches"][:3]):
            lines.append(f"  {i+1}. {m['customerName']} ({m['score']}%) — <code>add khach hang {m['customerID']}</code>")
    return lines
