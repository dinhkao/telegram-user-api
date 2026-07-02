// Trình nhập hoá đơn nâng cao — dùng chung cho OrderDetail (sửa) và CreateOrder
// (tạo mới). Dòng SP có autocomplete + tự lấy giá theo khách (/api/customer/price),
// điều chỉnh Chiết khấu/PVC/VAT (nút VAT 8%), tổng sống, nút Lưu + Tạo HĐ KiotViet.
// Parent quyết định onSave làm gì (invoice/update hay create-flow) và onCreateInvoice.
import { useEffect, useRef, useState } from "preact/hooks";
import { fetchCustomerPrice, searchProducts } from "../api";
import { money, parseMoney } from "../format";

export type EditorRow = { sp: string; sl: number; price: number; note?: string };
export type EditorPayload = { invoice: EditorRow[]; discount: number; pvc: number; vat: number };

// ── Ô nhập mã SP + gợi ý (autocomplete) ──────────────────────────────────
function ProductInput({ value, onChange, onCommit }: {
  value: string;
  onChange: (code: string) => void;      // gõ tới đâu cập nhật tới đó (cho phép mã tự do)
  onCommit: (code: string) => void;      // chọn gợi ý / rời ô → parent lấy giá
}) {
  const [q, setQ] = useState(value);
  const [sug, setSug] = useState<{ code: string; name: string }[]>([]);
  const [open, setOpen] = useState(false);
  const t = useRef<number>();
  useEffect(() => setQ(value), [value]);

  const input = (val: string) => {
    setQ(val);
    onChange(val);
    clearTimeout(t.current);
    if (!val.trim()) { setSug([]); setOpen(false); return; }
    t.current = window.setTimeout(async () => {
      const r = await searchProducts(val).catch(() => []);
      setSug(r);
      setOpen(r.length > 0);
    }, 200);
  };
  const pick = (code: string) => { setQ(code); setOpen(false); setSug([]); onChange(code); onCommit(code); };

  return (
    <div class="ac">
      <input
        value={q}
        placeholder="Mã SP"
        onInput={(e: any) => input(e.target.value)}
        onFocus={() => sug.length && setOpen(true)}
        onBlur={() => { setTimeout(() => setOpen(false), 150); onCommit(q); }}
      />
      {open && (
        <ul class="ac-list">
          {sug.map((s) => (
            <li key={s.code} onMouseDown={() => pick(s.code)}>
              <b>{s.code}</b>{s.name ? ` · ${s.name}` : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function InvoiceEditor({ customerId, invoice, discount, pvc, vat, onSave, onCreateInvoice, hasInvoice }: {
  customerId?: string;
  invoice: any[];
  discount?: number; pvc?: number; vat?: number;
  onSave: (payload: EditorPayload) => Promise<void> | void;
  onCreateInvoice?: () => Promise<void> | void;
  hasInvoice?: boolean;
}) {
  const [rows, setRows] = useState<EditorRow[]>([]);
  const [disc, setDisc] = useState(0);
  const [p, setP] = useState(0);
  const [v, setV] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setRows((invoice || []).map((it) => ({
      sp: it.sp || "", sl: Number(it.sl ?? it.quantity ?? 0) || 0,
      price: Number(it.price) || 0, note: it.note || "",
    })));
  }, [invoice]);
  useEffect(() => setDisc(Number(discount) || 0), [discount]);
  useEffect(() => setP(Number(pvc) || 0), [pvc]);
  useEffect(() => setV(Number(vat) || 0), [vat]);

  const tienHang = rows.reduce((s, r) => s + (r.price || 0) * (r.sl || 0), 0);
  const tong = tienHang - disc + p + v;

  const setRow = (i: number, f: string, val: any) => setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, [f]: val } : r)));
  const addRow = () => setRows((prev) => [...prev, { sp: "", sl: 1, price: 0, note: "" }]);
  const removeRow = (i: number) => setRows((prev) => prev.filter((_, idx) => idx !== i));

  // Tự lấy giá theo khách khi chốt mã SP — chỉ điền khi giá đang trống (không đè giá tay)
  const autoPrice = async (i: number, code: string) => {
    if (!customerId || !code.trim()) return;
    const price = await fetchCustomerPrice(customerId, code.trim()).catch(() => 0);
    if (price) setRows((prev) => prev.map((r, idx) => (idx === i && !r.price ? { ...r, price } : r)));
  };

  const run = async (fn: () => Promise<void> | void) => {
    setBusy(true);
    try { await fn(); } catch (e: any) { alert(e?.message || "Lỗi"); } finally { setBusy(false); }
  };
  const save = () => run(() => onSave({ invoice: rows.filter((r) => (r.sp || "").trim()), discount: disc, pvc: p, vat: v }));

  return (
    <div class="card">
      <b>Hoá đơn ({rows.length} món)</b>
      <table class="invoice-table">
        <thead>
          <tr><th>SP</th><th>SL</th><th>Giá</th><th>Tiền</th><th /></tr>
        </thead>
        <tbody>
          {rows.map((it, i) => (
            <tr key={i}>
              <td>
                <ProductInput value={it.sp} onChange={(c) => setRow(i, "sp", c)} onCommit={(c) => autoPrice(i, c)} />
                <input class="note-inp" placeholder="ghi chú" value={it.note || ""} onInput={(e: any) => setRow(i, "note", e.target.value)} />
              </td>
              <td class="num"><input class="narrow" inputMode="numeric" value={it.sl} onInput={(e: any) => setRow(i, "sl", parseMoney(e.target.value))} /></td>
              <td class="num"><input class="narrow" inputMode="numeric" value={it.price} onInput={(e: any) => setRow(i, "price", parseMoney(e.target.value))} /></td>
              <td class="num">{money((it.price || 0) * (it.sl || 0))}</td>
              <td><button class="btn small danger" onClick={() => removeRow(i)}>✕</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <button class="btn" onClick={addRow}>+ Thêm dòng</button>

      <div class="adj">
        <label>Tiền hàng<b class="num">{money(tienHang)}đ</b></label>
        <label>Chiết khấu<input class="narrow" inputMode="numeric" value={disc} onInput={(e: any) => setDisc(parseMoney(e.target.value))} /></label>
        <label>PVC (ship)<input class="narrow" inputMode="numeric" value={p} onInput={(e: any) => setP(parseMoney(e.target.value))} /></label>
        <label>VAT
          <span class="row">
            <input class="narrow" inputMode="numeric" value={v} onInput={(e: any) => setV(parseMoney(e.target.value))} />
            <button class="btn small" onClick={() => setV(Math.round(tienHang * 0.08))}>8%</button>
          </span>
        </label>
        <div class="row space total"><b>Tổng thanh toán</b><b class="money">{money(tong)}đ</b></div>
      </div>

      <div class="row">
        <button class="btn primary" disabled={busy} onClick={save}>{busy ? "Đang lưu…" : "💾 Lưu"}</button>
        {onCreateInvoice && (
          <button class="btn primary" disabled={busy} onClick={() => run(onCreateInvoice)}>
            {hasInvoice ? "🧾 Tạo lại HĐ" : "🧾 Tạo HĐ KiotViet"}
          </button>
        )}
      </div>
    </div>
  );
}
