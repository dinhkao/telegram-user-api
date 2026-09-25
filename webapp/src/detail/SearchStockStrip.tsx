// Dải TỒN KHO dưới ô tìm dashboard Đơn: chữ đang tìm là 1 MÃ SP (kể cả mã cũ) → hiện
// ngay tồn hiện tại "K10LV87 · Tồn 116 cây · 4 thùng", bấm mở #/kho/:code. Nguồn
// GET /api/orders/code-stock (cùng luật tồn trang Kho). Trễ 150ms + bỏ phản hồi lỗi
// thời; kho đổi (realtime inventory_changed/box_changed) → tải lại số.
import { useEffect, useRef, useState } from "preact/hooks";
import { getJSON } from "../api";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";

type CodeStock = { code: string; name: string; unit: string; stock: number; boxes: number; display?: { name: string; qty: number } };

const fmtN = (n: number) => n.toLocaleString("vi-VN", { maximumFractionDigits: 3 });

/** onProduct: báo lên trang mã SP (+ đơn vị) đang lọc — card hiện cột SL mã đó. */
export function SearchStockStrip({ search, onProduct }: { search: string; onProduct?: (p: { code: string; unit: string } | null) => void }) {
  const term = search.trim();
  const isCode = term.length >= 2 && !/\s/.test(term);
  const [p, setP] = useState<CodeStock | null>(null);
  const [tick, setTick] = useState(0);
  const seq = useRef(0);

  useEffect(() => {
    const my = ++seq.current;
    if (!isCode) { setP(null); return; }
    const t = setTimeout(async () => {
      try {
        const d = await getJSON(`/api/orders/code-stock?code=${encodeURIComponent(term)}`, { cache: false });
        if (my === seq.current) setP(d.product || null);
      } catch {
        if (my === seq.current) setP(null);   // dải tồn là phụ — lỗi thì ẩn
      }
    }, tick ? 400 : 150);
    return () => clearTimeout(t);
  }, [term, tick]);

  useEffect(() => { onProduct?.(isCode && p ? { code: p.code, unit: p.unit } : null); }, [p?.code, p?.unit, isCode]);

  useEffect(() => onRealtime((e: any) => {
    if (e.type === "inventory_changed" || e.type === "box_changed") setTick((x) => x + 1);
  }), []);

  if (!isCode || !p) return null;
  const out = p.stock <= 0;
  return (
    <a class={"sstock" + (out ? " out" : "")} href={`#/kho/${encodeURIComponent(p.code)}`}>
      <Icon name="box" size={16} class="sstock-ic" />
      <span class="sstock-main">
        <b>{p.code}</b>{p.name ? <span class="sstock-name"> · {p.name}</span> : null}
      </span>
      <span class="sstock-n">
        {out ? "Hết hàng" : <>Tồn <b>{fmtN(p.stock)}</b> {p.unit}</>}
        {!out && p.display ? <small> ≈ {fmtN(p.display.qty)} {p.display.name}</small> : null}
        {!out ? <small> · {p.boxes} thùng</small> : null}
      </span>
      <Icon name="chevronRight" size={14} />
    </a>
  );
}
