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

export function InvoiceTable({ items, discount, pvc, vat, debt, total, q, debtCtl }: {
  items: { sp: string; sl: number | string; price: number }[];
  discount?: number; pvc?: number; vat?: number; debt?: number | null;
  total?: string;   // tổng in sẵn từ KiotViet (nếu có) — ưu tiên dòng "Tổng thanh toán"
  q?: string;       // từ khoá tìm kiếm → tô sáng mã SP khớp
  debtCtl?: any;    // nút khoá 🔒 / 🔄 cập nhật nợ — render NGAY cạnh chữ "Nợ trước"
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
            <td>{hl(it.sp, q)}</td>
            <td class="num">{it.sl}</td>
            <td class="num">{money(it.price)}</td>
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
