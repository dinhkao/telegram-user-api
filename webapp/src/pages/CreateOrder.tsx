// Tạo đơn mới — 2 chế độ:
//  • Nhanh: gõ text tự do → /api/order/create (backend tự parse, như Telegram).
//  • Nâng cao: chọn khách → nhập từng dòng SP (tự lấy giá) + VAT/PVC/CK → tạo đơn
//    rồi lưu hoá đơn, chuyển sang trang chi tiết để bấm "Tạo HĐ KiotViet".
// Cần mạng (không queue). Bàn phím: preview DÍNH ĐỈNH + nút Tạo mini trong preview
// nên mọi thứ quan trọng luôn ở NỬA TRÊN màn hình (bàn phím không che).
import { useState, useEffect, useRef } from "preact/hooks";
import { postJSON, previewOrder, refreshCustomerDebt, getCustomerPriceList, type OrderPreview, type CustomerPriceList } from "../api";
import { money } from "../format";
import { InvoiceEditor, type EditorPayload } from "../detail/InvoiceEditor";
import { CustomerPicker } from "../detail/CustomerPicker";
import { useScrollLock } from "../useScrollLock";
import { Icon } from "../ui/Icon";
import { usePopupBack } from "../ui/usePopupBack";

const initial = (name: string) => (name.trim().charAt(0) || "?").toUpperCase();

// Giá rút gọn cho cột hẹp (chia đôi màn hình): 17000 → "17k", 25500 → "25,5k".
const moneyK = (v: number) =>
  v >= 1000 && v % 100 === 0 ? `${(v / 1000).toLocaleString("vi-VN")}k` : money(v);

// Nháp — text + khách đã chọn sống qua rời trang / reload app (localStorage).
// Xoá khi tạo đơn xong hoặc khi người dùng tự xoá hết.
const DRAFT_KEY = "co_draft";
const loadDraft = (): { text?: string; picked?: { key: string; name: string } | null } => {
  try { return JSON.parse(localStorage.getItem(DRAFT_KEY) || "null") || {}; } catch { return {}; }
};

export function CreateOrder() {
  const [mode, setMode] = useState<"advanced" | "quick">("quick");
  const [text, setText] = useState(() => loadDraft().text || "");
  const [customer, setCustomer] = useState<{ key: string; name: string } | null>(null);
  const [picked, setPicked] = useState<{ key: string; name: string } | null>(() => loadDraft().picked || null); // khách chọn tay ở tab Nhanh
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
  usePopupBack(plOpen, () => setPlOpen(false));
  const seq = useRef(0);
  const [showHint, setShowHint] = useState(false);
  const [typing, setTyping] = useState(false);   // ô nhập đang focus (bàn phím bật)
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Đang gõ (bàn phím bật) → giấu bottom-nav (body.co-kbd, styles.css) cho ô nhập
  // khỏi bị nav đè trên màn thấp; blur thì nav hiện lại.
  useEffect(() => {
    document.body.classList.toggle("co-kbd", typing);
    return () => document.body.classList.remove("co-kbd");
  }, [typing]);
  // Android WebView: bấm BACK khi bàn phím mở → bàn phím đóng nhưng KHÔNG có
  // popstate, textarea vẫn focus → layout chia đôi (.co-typing) kẹt lại dù bàn
  // phím đã tắt. Fix: khi đang gõ, nghe visualViewport resize CHỈ để phát hiện
  // bàn phím đóng (viewport cao TRỞ LẠI đáng kể) rồi blur() → typing=false, layout
  // gộp lại. KHÔNG dùng viewport để đo/đặt kích thước gì (chiều cao vẫn do CSS
  // quản — tránh giật, xem chú thích styles.css). Guard: chỉ blur khi viewport đã
  // từng THU NHỎ (hMin, lúc bàn phím bật) rồi cao lại >20% + >120px — chiều thu
  // nhỏ chỉ cập nhật hMin nên mở bàn phím / reflow chia cột không kích nhầm.
  useEffect(() => {
    if (!typing) return;
    const vv = window.visualViewport;
    if (!vv) return;
    let hMin = vv.height; // thấp nhất từng thấy trong phiên gõ này (bàn phím bật)
    const onResize = () => {
      const h = vv.height;
      if (h <= hMin) { hMin = h; return; }               // đang thu nhỏ → chỉ ghi nhớ
      if (h - hMin > 120 && h > hMin * 1.2) taRef.current?.blur(); // cao lại rõ rệt = bàn phím đóng
    };
    vv.addEventListener("resize", onResize);
    return () => vv.removeEventListener("resize", onResize);
  }, [typing]);

  // Lưu nháp mỗi lần đổi — rời trang / thoát app giữa chừng thì quay lại gõ tiếp.
  useEffect(() => {
    if (!text.trim() && !picked) localStorage.removeItem(DRAFT_KEY);
    else localStorage.setItem(DRAFT_KEY, JSON.stringify({ text, picked }));
  }, [text, picked]);

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
      localStorage.removeItem(DRAFT_KEY); // đơn đã tạo → bỏ nháp
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

  // Khối khách trong preview — avatar + tên + độ khớp + nợ (pill) + bảng giá
  const previewCustomer = () => {
    if (!preview) return null;
    const c = preview.customer;
    if (!c) {
      return (
        <div class="co-prev-nocust muted small">
          {preview.candidates.length
            ? <><Icon name="search" size={13} /> Có thể: {preview.candidates.map((x) => `${x.name} (${x.score}%)`).join(" · ")}</>
            : <><Icon name="user" size={13} /> Chưa nhận ra khách hàng</>}
        </div>
      );
    }
    const name = c.name || picked?.name || "Khách";
    const isLive = liveDebt?.id === c.id;
    const debt = isLive ? liveDebt!.debt : c.debt;
    return (
      <div class="co-prev-cust">
        <span class="co-avatar" aria-hidden="true">{initial(name)}</span>
        <div class="co-prev-cinfo">
          <b>{name}</b>
          <span class="muted small">
            {c.manual ? "Chọn tay" : `Khớp ${c.score}%`}
            {c.price_list_name && <> · {c.price_list_name}{" "}
              <button class="co-link" onClick={(e: any) => { e.preventDefault(); openPriceList(c.id); }}>Xem giá</button></>}
          </span>
        </div>
        {debtBusy && !isLive
          ? <span class="co-debt wait">Nợ…</span>
          : debt != null && <span class={"co-debt" + (debt > 0 ? " owe" : "")}>Nợ {money(debt)}đ{isLive ? " 🟢" : ""}</span>}
      </div>
    );
  };

  return (
    <div>
      {/* Chọn chế độ — segmented control. Giấu khi đang gõ (typing) để nhường
          chỗ dọc cho 2 cột chia đôi (chiều cao cột trong CSS đã trừ ít đi
          tương ứng — xem .co-typing .co-split trong styles.css). */}
      {!typing && (
      <div class="seg" role="tablist">
        <button class={mode === "quick" ? "seg-btn active" : "seg-btn"} onClick={() => setMode("quick")}>
          <Icon name="zap" size={15} /> Nhanh
        </button>
        <button class={mode === "advanced" ? "seg-btn active" : "seg-btn"} onClick={() => setMode("advanced")}>
          <Icon name="clipboard" size={15} /> Nâng cao
        </button>
      </div>
      )}

      {mode === "quick" ? (
        <div class={typing ? "co-typing" : ""}>
          {/* Chọn khách (tùy chọn) — đè lên tự nhận diện từ text */}
          <div class="co-cust">
            {picked ? (
              <div class="co-cust-picked">
                <span class="co-avatar" aria-hidden="true">{initial(picked.name)}</span>
                <b class="co-cust-name">{picked.name}</b>
                <button class="btn small ghost" onClick={() => setPicked(null)}>Đổi</button>
              </div>
            ) : (
              <CustomerPicker onPick={setPicked} placeholder="Khách hàng (tùy chọn — tự nhận từ text)" />
            )}
          </div>

          {/* Bình thường: preview TRÊN ô nhập. Đang gõ: chia đôi màn hình — ô nhập
              TRÁI + preview PHẢI, cả hai cao hết chỗ trên bàn phím, cuộn riêng
              từng ô → không bị cắt. Nút "Tạo" mini trong header preview. */}
          <div class="co-split">
          {(text.trim() || picked) && (
            <div class="co-preview">
              <div class="co-prev-head">
                <Icon name="eye" size={13} /> Xem trước
                {previewing && <span class="co-spin" aria-label="đang phân tích" />}
                {text.trim() !== "" && (
                  <button class="co-prev-go" disabled={busy} onClick={submitQuick}>
                    {busy ? "Đang tạo…" : "Tạo đơn ▸"}
                  </button>
                )}
              </div>
              {preview && (
                <>
                  {previewCustomer()}
                  {preview.invoice.length ? (
                    <table class="invoice-table co-items">
                      <tbody>
                        {preview.invoice.map((it, i) => (
                          <tr key={i}>
                            {/* .co-pmini: giá rút gọn cạnh mã SP — CHỈ hiện ở chế độ
                                chia đôi (cột đơn giá bị ẩn cho hẹp, xem styles.css) */}
                            <td>{it.sp} <span class="co-pmini">·{moneyK(it.price)}</span></td>
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
                    </table>
                  ) : (
                    <p class="co-prev-empty muted small">Chưa nhận ra sản phẩm nào — kiểm tra tên/mã SP.</p>
                  )}
                  {preview.invoice.length > 0 && (
                    <div class="co-total">
                      <span>Tổng cộng · {preview.invoice.length} SP</span>
                      <b>{money(preview.total)}đ</b>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          <textarea ref={taRef} class="co-input" placeholder={"Gõ đơn ở đây…\nlp\nk2l 1t\nk1l 1t 30\ndm180 1t 50 25000"} value={text}
            onFocus={() => setTyping(true)} onBlur={() => setTyping(false)}
            onInput={(e: any) => setText(e.target.value)} />
          </div>

          {err && <p class={err.startsWith("✅") ? "ok-msg" : "err-msg"}>{err}</p>}
          <button class="btn primary wide co-submit" disabled={busy || !text.trim()} onClick={submitQuick}>
            {busy ? "Đang tạo…" : preview?.invoice.length
              ? `Tạo đơn · ${preview.invoice.length} SP · ${money(preview.total)}đ`
              : "Tạo đơn"}
          </button>

          <button class="co-hint-toggle" onClick={() => setShowHint((v) => !v)}>
            <Icon name="info" size={14} /> Cách nhận diện <Icon name="chevronDown" size={13} class={"co-hint-chev" + (showHint ? " flip" : "")} />
          </button>
          {showHint && (
          <div class="co-hint muted">
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
          <p class="co-note muted small">📨 Đơn tạo từ web sẽ đăng vào kênh #don_hang và tạo topic Telegram như gõ tay.</p>
        </div>
      ) : (
        <div>
          <div class="co-cust card">
            <label>Khách hàng</label>
            {customer ? (
              <div class="co-cust-picked">
                <span class="co-avatar" aria-hidden="true">{initial(customer.name)}</span>
                <b class="co-cust-name">{customer.name}</b>
                <button class="btn small ghost" onClick={() => setCustomer(null)}>Đổi</button>
              </div>
            ) : (
              <>
                <CustomerPicker onPick={setCustomer} />
                <p class="muted small">Chọn khách để tự lấy giá theo bảng giá.</p>
              </>
            )}
          </div>
          <InvoiceEditor customerId={customer?.key} invoice={[]} onSave={createAdvanced} createMode />
          <p class="muted small">Bấm 💾 Lưu để tạo đơn; sang trang chi tiết bấm 🧾 Tạo HĐ KiotViet.</p>
          <p class="co-note muted small">📨 Đơn tạo từ web sẽ đăng vào kênh #don_hang và tạo topic Telegram như gõ tay.</p>
        </div>
      )}

      {plOpen && (
        <div class="modal-backdrop" onClick={() => setPlOpen(false)}>
          <div class="modal" onClick={(e: any) => e.stopPropagation()}>
            <div class="row space">
              <b><Icon name="clipboard" size={15} /> Bảng giá{priceList?.name ? `: ${priceList.name}` : ""}</b>
              <button class="btn small" onClick={() => setPlOpen(false)}><Icon name="close" size={14} /></button>
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
