// Tạo đơn mới — 2 chế độ:
//  • Nhanh: gõ text tự do → /api/order/create (backend tự parse, như Telegram).
//  • Nâng cao: chọn khách → nhập từng dòng SP (tự lấy giá) + VAT/PVC/CK → tạo đơn
//    rồi lưu hoá đơn, chuyển sang trang chi tiết để bấm "Tạo HĐ KiotViet".
// Cần mạng (không queue).
import { useState, useEffect, useRef } from "preact/hooks";
import { postJSON, previewOrder, refreshCustomerDebt, getCustomerPriceList, type OrderPreview, type CustomerPriceList } from "../api";
import { money } from "../format";
import { InvoiceEditor, type EditorPayload } from "../detail/InvoiceEditor";
import { CustomerPicker } from "../detail/CustomerPicker";
import { useScrollLock } from "../useScrollLock";

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
  const [priceList, setPriceList] = useState<CustomerPriceList | null>(null);
  const [plOpen, setPlOpen] = useState(false);
  const openPriceList = async (key: string) => {
    setPlOpen(true);
    setPriceList(null);
    try { setPriceList(await getCustomerPriceList(key)); } catch { /* ignore */ }
  };
  useScrollLock(plOpen); // khoá cuộn nền khi popup bảng giá mở
  const seq = useRef(0);
  const [showHint, setShowHint] = useState(false);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Ô nhập CHỮ TO — trống thì cực to, gõ nhiều thì tự thu nhỏ font để vừa ô.
  // Chiều cao ô do CSS quản (ổn định, KHÔNG đo viewport) → không giật khi bàn phím
  // bật/tắt. Chỉ đo nội dung so với chiều cao CSS của ô rồi giảm font.
  const fitFont = () => {
    const ta = taRef.current;
    if (!ta || mode !== "quick") return;
    let fs = 42;                                         // super to khi trống
    ta.style.fontSize = fs + "px";
    while (ta.scrollHeight > ta.clientHeight && fs > 18) { fs -= 1; ta.style.fontSize = fs + "px"; }
  };
  // Chỉ chạy khi NỘI DUNG đổi (gõ) — không bám sự kiện bàn phím/cuộn (nguồn gây giật).
  useEffect(() => {
    const r = requestAnimationFrame(fitFont);
    return () => cancelAnimationFrame(r);
  }, [text, mode]);
  // Xoay màn hình → cân lại 1 lần (debounce), không nghe visualViewport.
  useEffect(() => {
    let t: any;
    const on = () => { clearTimeout(t); t = setTimeout(() => requestAnimationFrame(fitFont), 200); };
    window.addEventListener("orientationchange", on);
    return () => { clearTimeout(t); window.removeEventListener("orientationchange", on); };
  }, []);

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
      // Đăng vào kênh #don_hang → tạo topic Telegram + đơn (như gõ tay trên Telegram)
      const r = await postJSON("/api/order/create", { text: text.trim() });
      if (r.thread_id) window.location.hash = `#/order/${r.thread_id}`;
      else { setErr("✅ Đã gửi vào #don_hang — đang tạo đơn, sẽ hiện ở danh sách."); window.location.hash = "#/"; }
    } catch (ex: any) { setErr(ex.message); } finally { setBusy(false); }
  };

  // Nâng cao: đăng tên khách vào #don_hang (tạo topic + đơn) → lưu hoá đơn → chi tiết
  const createAdvanced = async (payload: EditorPayload) => {
    if (!customer) throw new Error("Chọn khách hàng trước");
    if (!payload.invoice.length) throw new Error("Thêm ít nhất 1 sản phẩm");
    const r = await postJSON("/api/order/create", { text: customer.name });
    const tid = r.thread_id;
    if (!tid) throw new Error("Đơn đang được tạo trên Telegram — chờ vài giây rồi thử lại");
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

          {/* Xem trước Ở TRÊN ô nhập, DÍNH ĐỈNH → luôn thấy khi gõ (bàn phím không che) */}
          {(text.trim() || picked) && (
            <div class="preview-box co-preview">
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
                          <div class="muted small">
                            📋 Bảng giá: {preview.customer.price_list_name}{" "}
                            <button class="btn small" onClick={(e: any) => { e.preventDefault(); openPriceList(preview.customer!.id); }}>Xem giá</button>
                          </div>
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
                            <td class="num">
                              {money(it.price)}đ
                              {it.list_price != null && it.list_price > 0 && it.list_price !== it.price && (
                                <div class="old-price">{money(it.list_price)}đ</div>
                              )}
                            </td>
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

          <textarea ref={taRef} class="co-input" placeholder={"Gõ đơn ở đây…\nlp\nk2l 1t\nk1l 1t 30\ndm180 1t 50 25000"} value={text} onInput={(e: any) => setText(e.target.value)} />

          <button class="btn small hint-toggle" onClick={() => setShowHint((v) => !v)}>
            💡 Cách nhận diện {showHint ? "▲" : "▼"}
          </button>
          {showHint && (
          <div class="muted small hint">
            <ul class="hint-list">
              <li><b>Khách:</b> tên khách (tự gán nếu khớp cao — kèm nợ &amp; bảng giá), hoặc chọn ở ô trên.</li>
              <li><b>Sản phẩm:</b> mỗi dòng <code>&lt;mã SP&gt; &lt;số lượng&gt;</code> — mã trước, SL sau (số đứng trước mã bị bỏ qua).</li>
              <li>
                <b>Số lượng / quy cách:</b> <code>K2L 10</code> = 10 cái ·
                {" "}<code>5t</code> = 5 thùng, đổi số/thùng bằng <code>5t 60</code> ·
                {" "}<code>3b</code> = 3 bịch, đổi số/bịch bằng <code>3b 12</code> ·
                {" "}<code>2t3b</code> = 2 thùng 3 bịch.
              </li>
              <li>
                <b>Mặc định số/thùng:</b> 50 · DM50 = 100 · KDXDB/KGL/KMT/KMD/KHDX = 5 · KDDT = 12.
                {" "}<b>Số/bịch:</b> 10 · KDDT = 3 · DM180 1 lốc = 12.
              </li>
              <li><b>Giá:</b> tự lấy theo bảng giá khách; nhập số sau SL để <b>ghi đè giá</b>, vd <code>K2L 10 25000</code> = 10 cái, giá 25.000.</li>
            </ul>
          </div>
          )}

          {err && <p class={err.startsWith("✅") ? "ok-msg" : "error"}>{err}</p>}
          <button class="btn primary wide co-submit" disabled={busy} onClick={submitQuick}>{busy ? "Đang tạo…" : "Tạo đơn"}</button>
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
      <p class="muted small">📨 Đơn tạo từ web sẽ đăng vào kênh #don_hang và tạo topic Telegram như gõ tay.</p>

      {plOpen && (
        <div class="modal-backdrop" onClick={() => setPlOpen(false)}>
          <div class="modal" onClick={(e: any) => e.stopPropagation()}>
            <div class="row space">
              <b>📋 Bảng giá{priceList?.name ? `: ${priceList.name}` : ""}</b>
              <button class="btn small" onClick={() => setPlOpen(false)}>✕</button>
            </div>
            {!priceList ? (
              <p class="muted small">Đang tải…</p>
            ) : priceList.items.length ? (
              <div class="pl-scroll">
                <table class="invoice-table">
                  <tbody>
                    {priceList.items.map((it) => (
                      <tr key={it.sp}><td>{it.sp}</td><td class="num">{money(it.price)}đ</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p class="muted small">Bảng giá trống.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
