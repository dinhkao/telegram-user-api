// Bảng hoá đơn (y chang summary KiotViet) — dùng chung cho card dashboard và
// chế độ XEM ở trang chi tiết. Tính từ items + phí (CK/PVC/VAT) + nợ.
import { money, foldVN } from "../format";

// Tô sáng cụm khớp tìm kiếm (KHÔNG DẤU) trong 1 chuỗi (vd mã SP)
function hl(text: string, q?: string) {
  const s = text || "";
  const query = (q || "").trim();
  if (!query) return s;
  const fs = foldVN(s);
  const fq = foldVN(query);
  if (!fq) return s;
  const out: any[] = [];
  let from = 0, idx: number, key = 0;
  while ((idx = fs.indexOf(fq, from)) !== -1) {
    if (idx > from) out.push(s.slice(from, idx));
    out.push(<mark key={key++}>{s.slice(idx, idx + fq.length)}</mark>);
    from = idx + fq.length;
  }
  out.push(s.slice(from));
  return out;
}

export function InvoiceTable({ items, discount, pvc, vat, debt, total, q }: {
  items: { sp: string; sl: number | string; price: number }[];
  discount?: number; pvc?: number; vat?: number; debt?: number | null;
  total?: string;   // tổng in sẵn từ KiotViet (nếu có) — ưu tiên dòng "Tổng thanh toán"
  q?: string;       // từ khoá tìm kiếm → tô sáng mã SP khớp
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
        {!hasFees && d === 0 ? (
          <tr class="tot"><td colSpan={3} class="lbl">Tổng</td><td class="num">{money(tongTT)}đ</td></tr>
        ) : (
          <>
            <tr class="sub"><td colSpan={3} class="lbl">Tổng tiền hàng</td><td class="num">{money(tienHang)}</td></tr>
            {p ? <tr class="sub"><td colSpan={3} class="lbl">PVC</td><td class="num">+{money(p)}</td></tr> : null}
            {v ? <tr class="sub"><td colSpan={3} class="lbl">VAT</td><td class="num">+{money(v)}</td></tr> : null}
            {disc ? <tr class="sub"><td colSpan={3} class="lbl">Giảm giá</td><td class="num">−{money(disc)}</td></tr> : null}
            {d !== 0 && hasFees ? <tr class="sub"><td colSpan={3} class="lbl">Tổng đơn này</td><td class="num">{money(tongDon)}</td></tr> : null}
            {d !== 0 ? <tr class="sub debt"><td colSpan={3} class="lbl">Nợ trước</td><td class="num">{money(d)}</td></tr> : null}
            <tr class="tot"><td colSpan={3} class="lbl">Tổng thanh toán</td><td class="num">{money(tongTT)}đ</td></tr>
          </>
        )}
      </tbody>
    </table>
  );
}
