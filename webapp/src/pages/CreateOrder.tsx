// Tạo đơn mới — 2 chế độ:
//  • Nhanh: gõ text tự do → /api/order/create (backend tự parse, như Telegram).
//  • Nâng cao: chọn khách → nhập từng dòng SP (tự lấy giá) + VAT/PVC/CK → tạo đơn
//    rồi lưu hoá đơn, chuyển sang trang chi tiết để bấm "Tạo HĐ KiotViet".
// Cần mạng (không queue).
import { useState } from "preact/hooks";
import { postJSON } from "../api";
import { InvoiceEditor, type EditorPayload } from "../detail/InvoiceEditor";
import { CustomerPicker } from "../detail/CustomerPicker";

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
          <InvoiceEditor customerId={customer?.key} invoice={[]} onSave={createAdvanced} createMode />
          <p class="muted small">Bấm 💾 Lưu để tạo đơn; sang trang chi tiết bấm 🧾 Tạo HĐ KiotViet.</p>
        </div>
      )}
      <p class="muted small">⚠️ Đơn tạo từ web chỉ nằm trong hệ thống — không tạo topic Telegram.</p>
    </div>
  );
}
