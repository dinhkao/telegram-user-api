// Tìm bằng MÃ SP mà nội dung đơn KHÔNG ghi mã đó (khách gõ tên/biệt danh, hoá đơn mới
// ra mã) → card dashboard hiện thêm dòng hàng khớp, vd "K10LV87 30", để thấy vì sao
// đơn lọt kết quả. Khớp y như server (chuỗi con không dấu trên mã SP); q có khoảng
// trắng thì không phải tìm theo mã → bỏ qua.
import { foldVN, fmtQty } from "../format";
import type { OrderRow } from "./OrderCards";

export function searchHitItems(o: OrderRow, search: string): { sp: string; sl: number | string }[] {
  const q = foldVN(search.trim());
  if (q.length < 2 || /\s/.test(q)) return [];
  const text = foldVN(o.text || "");
  return (o.invoice_items || []).filter((it) => {
    const sp = foldVN(String(it.sp || ""));
    return sp.includes(q) && !text.includes(sp);
  });
}

export function SearchHitItems({ o, search }: { o: OrderRow; search: string }) {
  const hits = searchHitItems(o, search);
  if (!hits.length) return null;
  return (
    <>
      {hits.map((it, i) => (
        <span class="hit-sp" key={i}>{it.sp} {typeof it.sl === "number" ? fmtQty(it.sl) : it.sl}</span>
      ))}
    </>
  );
}
