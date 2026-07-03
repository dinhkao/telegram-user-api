// Tạo đơn mới — 2 chế độ:
//  • Nhanh: gõ text tự do → /api/order/create (backend tự parse, như Telegram).
//  • Nâng cao: chọn khách → nhập từng dòng SP (tự lấy giá) + VAT/PVC/CK → tạo đơn
//    rồi lưu hoá đơn, chuyển sang trang chi tiết để bấm "Tạo HĐ KiotViet".
// Cần mạng (không queue).
import { useState, useEffect, useRef } from "preact/hooks";
import { postJSON, previewOrder, refreshCustomerDebt, type OrderPreview } from "../api";
import { money } from "../format";
import { InvoiceEditor, type EditorPayload } from "../detail/InvoiceEditor";
import { CustomerPicker } from "../detail/CustomerPicker";

export function CreateOrder() {
  const [mode, setMode] = useState<"advanced" | "quick">("quick");
  const [text, setText] = useState("");
  const [customer, setCustomer] = useState<{ key: string; name: string } | null>(null);
  const [picked, setPicked] = useState<{ key: string; name: string } | null>(null); // khách chọn tay ở tab Nhanh
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [preview, setPreview] = useState<OrderPreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [liveDebt, setLiveDebt] = useState<{ id: string; debt: number | null } | null>(null);
  const [debtBusy, setDebtBusy] = useState(false);
  const seq = useRef(0);

  // Khách vừa nhận diện → kéo nợ MỚI từ KiotViet 1 lần (theo id, không mỗi phím)
  useEffect(() => {
    const id = preview?.customer?.id;
    if (!id) { setLiveDebt(null); return; }
    let alive = true;
    setDebtBusy(true);
    refreshCustomerDebt(id)
      .then((c) => { if (alive) setLiveDebt({ id, debt: c.debt }); })
      .catch(() => {})
      .finally(() => { if (alive) setDebtBusy(false); });
    return () => { alive = false; };
  }, [preview?.customer?.id]);

  // Xem trước tức thời khi gõ ở tab Nhanh — không delay; seq chặn kết quả cũ về sau
  useEffect(() => {
    if (mode !== "quick") { setPreview(null); return; }
    const t = text.trim();
    if (!t && !picked) { setPreview(null); setPreviewing(false); return; }
    const my = ++seq.current;
    setPreviewing(true);
    previewOrder(t, picked?.key)
      .then((r) => { if (my === seq.current) setPreview(r); })
      .catch(() => { if (my === seq.current) setPreview(null); })
      .finally(() => { if (my === seq.current) setPreviewing(false); });
  }, [text, mode, picked?.key]);

  const submitQuick = async () => {
    if (!text.trim()) return setErr("Nhập nội dung đơn");
    setBusy(true); setErr("");
    try {
      const body: any = { text: text.trim() };
      if (picked) body.customer_key = picked.key; // khách chọn tay → gán luôn
      const r = await postJSON("/api/order/create", body);
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
        <button class={mode === "quick" ? "chip active" : "chip"} onClick={() => setMode("quick")}>Nhanh (text)</button>
        <button class={mode === "advanced" ? "chip active" : "chip"} onClick={() => setMode("advanced")}>Nâng cao</button>
      </div>

      {mode === "quick" ? (
        <div class="card">
          {/* Chọn khách (tùy chọn) — đè lên tự nhận diện từ text */}
          <div class="quick-cust">
            {picked ? (
              <div class="picked-cust">
                ✓ <b>{picked.name}</b>
                <button class="btn small" onClick={() => setPicked(null)}>Đổi</button>
              </div>
            ) : (
              <>
                <label>Khách hàng (tùy chọn — để trống thì tự nhận từ text)</label>
                <CustomerPicker onPick={setPicked} />
              </>
            )}
          </div>

          {/* Xem trước Ở TRÊN ô nhập → bàn phím mobile không che */}
          {(text.trim() || picked) && (
            <div class="preview-box">
              <div class="preview-head">
                🔎 Xem trước {previewing && <span class="muted small">đang phân tích…</span>}
              </div>
              {preview && (
                <>
                  <div class="preview-cust">
                    {preview.customer ? (
                      <>
                        👤 <b>{preview.customer.name || picked?.name || "Khách"}</b>{" "}
                        <span class="muted small">{preview.customer.manual ? "(chọn tay)" : `(${preview.customer.score}%)`}</span>
                        {(() => {
                          const isLive = liveDebt?.id === preview.customer!.id;
                          const debt = isLive ? liveDebt!.debt : preview.customer!.debt;
                          if (debtBusy && !isLive) return <span class="muted small"> · Nợ: đang lấy KiotViet…</span>;
                          if (debt == null) return null;
                          return (
                            <span class={debt > 0 ? "owe" : "muted small"}> · Nợ: {money(debt)}đ {isLive ? "🟢" : ""}</span>
                          );
                        })()}
                        {preview.customer.price_list_name && (
                          <div class="muted small">📋 Bảng giá: {preview.customer.price_list_name}</div>
                        )}
                      </>
                    ) : preview.candidates.length ? (
                      <span class="muted small">🔍 Có thể: {preview.candidates.map((c) => `${c.name} (${c.score}%)`).join(" · ")}</span>
                    ) : (
                      <span class="muted small">👤 Chưa nhận ra khách hàng</span>
                    )}
                  </div>
                  {preview.invoice.length ? (
                    <table class="invoice-table">
                      <tbody>
                        {preview.invoice.map((it, i) => (
                          <tr key={i}>
                            <td>{it.sp}</td>
                            <td class="num">x{it.sl}</td>
                            <td class="num">{money(it.price)}đ</td>
                            <td class="num"><b>{money(it.sub)}đ</b></td>
                          </tr>
                        ))}
                      </tbody>
                      <tfoot>
                        <tr>
                          <td colSpan={3}>Tổng cộng</td>
                          <td class="num"><b class="money">{money(preview.total)}đ</b></td>
                        </tr>
                      </tfoot>
                    </table>
                  ) : (
                    <p class="muted small">Chưa nhận ra sản phẩm nào — kiểm tra tên/mã SP.</p>
                  )}
                </>
              )}
            </div>
          )}

          <textarea rows={8} placeholder={"vd:\nLoan Phú\nK2L 10\nKDDT 5t\nKGL 3b 12"} value={text} onInput={(e: any) => setText(e.target.value)} />

          <div class="muted small hint">
            💡 <b>Cách nhận diện:</b>
            <ul class="hint-list">
              <li><b>Khách:</b> tên khách (tự gán nếu khớp cao — kèm nợ &amp; bảng giá), hoặc chọn ở ô trên.</li>
              <li><b>Sản phẩm:</b> mỗi dòng <code>&lt;mã SP&gt; &lt;số lượng&gt;</code> — mã trước, SL sau (số đứng trước mã bị bỏ qua).</li>
              <li>
                <b>Số lượng / quy cách:</b> <code>K2L 10</code> = 10 cái ·
                {" "}<code>5t</code> = 5 thùng (50 cái/thùng), đổi bằng <code>5t 60</code> ·
                {" "}<code>3b</code> = 3 bịch (3 cái/bịch), đổi bằng <code>3b 12</code> ·
                {" "}<code>2t3b</code> = 2 thùng 3 bịch.
              </li>
              <li><b>Giá:</b> tự lấy theo bảng giá của khách (không nhập giá trong text).</li>
            </ul>
          </div>

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
