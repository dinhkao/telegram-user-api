// Bảng hoá đơn (y chang summary KiotViet) — dùng chung cho card dashboard và
// chế độ XEM ở trang chi tiết. Tính từ items + phí (CK/PVC/VAT) + nợ.
import { money, foldVN } from "../format";

// Tô sáng KHÔNG DẤU trong 1 chuỗi (vd mã SP) — tách q theo khoảng trắng, tô TỪNG TỪ
// ở mọi vị trí (khớp cách tìm kiếm ghép nhiều trường). foldVN giữ nguyên độ dài.
function hl(text: string, q?: string) {
  const s = text || "";
  const tokens = (q || "").trim().split(/\s+/).map(foldVN).filter((t) => t.length >= 1);
  if (!tokens.length) return s;
  const fs = foldVN(s);
  const ranges: [number, number][] = [];
  for (const t of tokens) {
    let from = 0, idx: number;
    while ((idx = fs.indexOf(t, from)) !== -1) { ranges.push([idx, idx + t.length]); from = idx + t.length; }
  }
  if (!ranges.length) return s;
  ranges.sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [];
  for (const r of ranges) {
    const last = merged[merged.length - 1];
    if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]);
    else merged.push([r[0], r[1]]);
  }
  const out: any[] = [];
  let pos = 0, key = 0;
  for (const [a, b] of merged) {
    if (a > pos) out.push(s.slice(pos, a));
    out.push(<mark key={key++}>{s.slice(a, b)}</mark>);
    pos = b;
  }
  if (pos < s.length) out.push(s.slice(pos));
  return out;
}

// Nguồn gốc đơn giá (server order_store/price_origin): = đơn trước / bảng giá / ai nhập.
type PriceOrigin = { price_src?: "last" | "list" | "manual"; price_from?: number; price_from_date?: string; price_by?: string; price_backfill?: number };
function PriceOriginNote({ it }: { it: PriceOrigin }) {
  if (it.price_src === "last") {
    const label = `= đơn trước${it.price_from_date ? ` ${it.price_from_date}` : ""}`;
    return it.price_from
      ? <a class="po po-last" href={`#/order/${it.price_from}`} title="Giá tự lấy theo lần khách mua gần nhất — mở đơn đó">{label}</a>
      : <span class="po po-last">{label}</span>;
  }
  if (it.price_src === "list") return <span class="po po-list" title="Giá tự lấy theo bảng giá của khách">bảng giá</span>;
  if (it.price_src === "manual") {
    const t = it.price_backfill ? "Đơn cũ — suy từ dữ liệu: giá không trùng đơn trước/bảng giá, không rõ ai nhập" : "Giá do người dùng tự nhập";
    return <span class="po po-manual" title={t}>✎ {it.price_by ? `${it.price_by} nhập` : "nhập tay"}</span>;
  }
  return null;
}

export function InvoiceTable({ items, discount, pvc, vat, debt, total, q, debtCtl, linkSp, showOrigin }: {
  items: ({ sp: string; sl: number | string; price: number } & PriceOrigin)[];
  discount?: number; pvc?: number; vat?: number; debt?: number | null;
  total?: string;   // tổng in sẵn từ KiotViet (nếu có) — ưu tiên dòng "Tổng thanh toán"
  q?: string;       // từ khoá tìm kiếm → tô sáng mã SP khớp
  debtCtl?: any;    // nút khoá 🔒 / 🔄 cập nhật nợ — render NGAY cạnh chữ "Nợ trước"
  linkSp?: boolean; // mã SP bấm được → #/kho/<mã> (BẬT ở trang chi tiết đơn; TẮT ở card
                    // dashboard vì cả card là 1 nút mở đơn, link con sẽ nuốt cú chạm)
  showOrigin?: boolean; // ghi chú nguồn đơn giá dưới ô Giá (trang chi tiết đơn)
}) {
  const list = items || [];
  const tienHang = list.reduce((s, it) => s + (Number(it.price) || 0) * (Number(it.sl) || 0), 0);
  const p = pvc || 0, v = vat || 0, disc = discount || 0;
  const d = Number(debt) || 0;
  const hasFees = !!(p || v || disc);
  const tongDon = tienHang + p + v - disc;
  const tongTT = tongDon + d;
  return (
    <table class="inv-mini">
      <thead>
        <tr><th>SP</th><th class="num">SL</th><th class="num">Giá</th><th class="num">Tiền</th></tr>
      </thead>
      <tbody>
        {list.map((it, i) => (
          <tr key={i}>
            <td>{linkSp && String(it.sp || "").trim()
              ? <a class="pt-inl" href={`#/kho/${encodeURIComponent(String(it.sp).trim())}`}
                title="Mở trang sản phẩm">{hl(it.sp, q)}</a>
              : hl(it.sp, q)}</td>
            <td class="num">{it.sl}</td>
            <td class="num">{money(it.price)}{showOrigin ? <PriceOriginNote it={it} /> : null}</td>
            <td class="num">{money((Number(it.price) || 0) * (Number(it.sl) || 0))}</td>
          </tr>
        ))}
        {!hasFees && d === 0 && !debtCtl ? (
          <tr class="tot"><td colSpan={3} class="lbl">Tổng</td><td class="num">{money(tongTT)}</td></tr>
        ) : (
          <>
            <tr class="sub"><td colSpan={3} class="lbl">Tổng tiền hàng</td><td class="num">{money(tienHang)}</td></tr>
            {p ? <tr class="sub"><td colSpan={3} class="lbl">PVC</td><td class="num">+{money(p)}</td></tr> : null}
            {v ? <tr class="sub"><td colSpan={3} class="lbl">VAT</td><td class="num">+{money(v)}</td></tr> : null}
            {disc ? <tr class="sub"><td colSpan={3} class="lbl">Giảm giá</td><td class="num">−{money(disc)}</td></tr> : null}
            {d !== 0 && hasFees ? <tr class="sub"><td colSpan={3} class="lbl">Tổng đơn này</td><td class="num">{money(tongDon)}</td></tr> : null}
            {(d !== 0 || debtCtl) ? <tr class="sub"><td colSpan={3} class="lbl">Nợ trước{debtCtl ? <span class="debt-ctl">{debtCtl}</span> : null}</td><td class="num">{d !== 0 ? money(d) : <span class="muted">—</span>}</td></tr> : null}
            <tr class="tot"><td colSpan={3} class="lbl">Tổng thanh toán</td><td class="num">{money(tongTT)}</td></tr>
          </>
        )}
      </tbody>
    </table>
  );
}
