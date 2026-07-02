// Tạo đơn mới — 2 chế độ:
//  • Nhanh: gõ text tự do → /api/order/create (backend tự parse, như Telegram).
//  • Nâng cao: chọn khách → nhập từng dòng SP (tự lấy giá) + VAT/PVC/CK → tạo đơn
//    rồi lưu hoá đơn, chuyển sang trang chi tiết để bấm "Tạo HĐ KiotViet".
// Cần mạng (không queue).
import { useRef, useState } from "preact/hooks";
import { getJSON, postJSON } from "../api";
import { money } from "../format";
import { InvoiceEditor, type EditorPayload } from "../detail/InvoiceEditor";

// Ô tìm + chọn khách hàng (autocomplete /api/customers)
function CustomerPicker({ onPick }: { onPick: (c: { key: string; name: string } | null) => void }) {
  const [q, setQ] = useState("");
  const [sug, setSug] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const t = useRef<number>();
  const input = (v: string) => {
    setQ(v);
    onPick(null);
    clearTimeout(t.current);
    if (!v.trim()) { setSug([]); setOpen(false); return; }
    t.current = window.setTimeout(async () => {
      const d = await getJSON(`/api/customers?search=${encodeURIComponent(v)}&limit=10`, { cache: false }).catch(() => ({ customers: [] }));
      setSug(d.customers || []);
      setOpen((d.customers || []).length > 0);
    }, 250);
  };
  const pick = (c: any) => { setQ(c.name); setOpen(false); onPick({ key: c.key, name: c.name }); };
  return (
    <div class="ac">
      <input value={q} placeholder="🔍 Tìm khách hàng" onInput={(e: any) => input(e.target.value)} onBlur={() => setTimeout(() => setOpen(false), 150)} />
      {open && (
        <ul class="ac-list">
          {sug.map((c) => (
            <li key={c.key} onMouseDown={() => pick(c)}><b>{c.name}</b>{c.debt ? ` · nợ ${money(c.debt)}đ` : ""}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function CreateOrder() {
  const [mode, setMode] = useState<"advanced" | "quick">("advanced");
  const [text, setText] = useState("");
  const [customer, setCustomer] = useState<{ key: string; name: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submitQuick = async () => {
    if (!text.trim()) return setErr("Nhập nội dung đơn");
    setBusy(true); setErr("");
    try {
      const r = await postJSON("/api/order/create", { text: text.trim() });
      window.location.hash = `#/order/${r.thread_id}`;
    } catch (ex: any) { setErr(ex.message); } finally { setBusy(false); }
  };

  // Nâng cao: tạo đơn (gán khách) → lưu hoá đơn + điều chỉnh → sang trang chi tiết
  const createAdvanced = async (payload: EditorPayload) => {
    if (!customer) throw new Error("Chọn khách hàng trước");
    if (!payload.invoice.length) throw new Error("Thêm ít nhất 1 sản phẩm");
    const r = await postJSON("/api/order/create", { text: customer.name, customer_key: customer.key });
    const tid = r.thread_id;
    await postJSON("/api/order/invoice/update", { thread_id: tid, ...payload });
    window.location.hash = `#/order/${tid}`;
  };

  return (
    <div>
      <h2>➕ Tạo đơn mới</h2>
      <div class="chips">
        <button class={mode === "advanced" ? "chip active" : "chip"} onClick={() => setMode("advanced")}>Nâng cao</button>
        <button class={mode === "quick" ? "chip active" : "chip"} onClick={() => setMode("quick")}>Nhanh (text)</button>
      </div>

      {mode === "quick" ? (
        <div class="card">
          <p class="muted small">Gõ như nhắn Telegram: tên khách + các dòng sản phẩm. Hệ thống tự nhận khách và parse.</p>
          <textarea rows={10} placeholder={"vd:\nchị Hoa chợ Xóm Mới\n2 thùng KLC 350\n5kg C40 60"} value={text} onInput={(e: any) => setText(e.target.value)} />
          {err && <p class="error">{err}</p>}
          <button class="btn primary wide" disabled={busy} onClick={submitQuick}>{busy ? "Đang tạo…" : "Tạo đơn"}</button>
        </div>
      ) : (
        <div>
          <div class="card">
            <label>Khách hàng</label>
            <CustomerPicker onPick={setCustomer} />
            {customer ? <p class="muted small">✓ {customer.name}</p> : <p class="muted small">Chọn khách để tự lấy giá theo bảng giá.</p>}
          </div>
          <InvoiceEditor customerId={customer?.key} invoice={[]} onSave={createAdvanced} />
          <p class="muted small">Bấm 💾 Lưu để tạo đơn; sang trang chi tiết bấm 🧾 Tạo HĐ KiotViet.</p>
        </div>
      )}
      <p class="muted small">⚠️ Đơn tạo từ web chỉ nằm trong hệ thống — không tạo topic Telegram.</p>
    </div>
  );
}
