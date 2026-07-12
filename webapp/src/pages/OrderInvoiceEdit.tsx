// Trang "Sửa hoá đơn" (#/order/:id/hoa-don) — 2 TAB như trang tạo đơn, cùng sửa
// MỘT hoá đơn (qua lại tab không mất nội dung đang sửa — 2 tab cùng mount, chỉ ẩn):
//  • ⚡ Nhanh: sửa TEXT đơn + xem trước parse sống (khách + SP + tổng). Lưu qua
//    /api/order/fix → server nhận diện lại KHÁCH + SP theo bảng giá (như lệnh fix
//    Telegram) — preview mô phỏng đúng fix: khách nhận từ text, không nhận ra thì
//    giữ khách hiện tại; text nêu khách khác → cảnh báo sẽ ĐỔI khách.
//  • 📋 Nâng cao: ① Khách hàng (nợ KiotViet + bảng giá + Đổi khách qua
//    /api/order/assign-customer) → ② InvoiceEditor lấy giá theo khách bước 1 —
//    đổi khách là chú thích giá bảng/gợi ý giá cập nhật ngay.
// Mọi thao tác HĐ KiotViet (tạo/xem/in/xoá/kéo nợ) nằm ở khối Hoá đơn của
// OrderDetail. Đơn đã có HĐ KiotViet / chốt kho → khoá cả 2 tab.
import { useEffect, useRef, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { getJSON, postJSON, lockInvoiceEdit, unlockInvoiceEdit, previewOrder, refreshCustomerDebt, type OrderPreview } from "../api";
import { money, moneyK, initial } from "../format";
import { InvoiceEditor, type EditorPayload } from "../detail/InvoiceEditor";
import { CustomerPicker } from "../detail/CustomerPicker";
import { PriceListModal } from "../detail/PriceListModal";
import { invalidateListCache } from "./OrdersList";
import { toast } from "../ui/feedback";
import { Loading, ErrorState } from "../ui/states";
import { Icon } from "../ui/Icon";
import { useTypingSplit } from "../ui/useTypingSplit";

export function OrderInvoiceEdit({ threadId }: { threadId: string }) {
  const [detail, setDetail] = useState<any>(null);
  const [err, setErr] = useState("");
  const [editHolder, setEditHolder] = useState<string | null>(null);   // NGƯỜI KHÁC đang sửa
  const [mode, setMode] = useState<"quick" | "advanced">("quick");
  const [busy, setBusy] = useState(false);
  // tab Nâng cao — bước 1
  const [changingCust, setChangingCust] = useState(false);             // đang mở ô đổi khách
  const [cust, setCust] = useState<OrderPreview["customer"]>(null);    // nợ + bảng giá khách hiện tại
  const [plCust, setPlCust] = useState<string | null>(null);           // popup bảng giá
  // tab Nhanh — text + preview
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<OrderPreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [liveDebt, setLiveDebt] = useState<{ id: string; debt: number | null } | null>(null);
  const seq = useRef(0);
  const seededText = useRef(false);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const { typing, setTyping, exitTypingOnOutsideTap } = useTypingSplit(taRef);

  const reload = async () => {
    try { setDetail(await getJSON(`/api/order/${threadId}`)); setErr(""); }
    catch (ex: any) { setErr(ex.message); }
  };
  useEffect(() => { reload(); }, [threadId]);

  const j = detail?.data || {};
  const custKey: string = j.khach_hang_id || j.khID || "";
  const custName: string = j.customer_name || "";
  const origText: string = j.text || j.text_raw || "";
  const hasInvoice = !!j.kiotvietInvoiceID;
  const stockLocked = !!j.stock_confirmed;   // đã chốt xuất kho → khoá dù đã xoá HĐ
  const locked = hasInvoice || stockLocked;
  const editable = !!detail && !locked;      // chỉ giữ khoá khi đơn còn sửa được
  const canChange = editable && !editHolder; // đổi khách: server cũng cấm khi có HĐ KiotViet
  const textChanged = !!detail && text.trim() !== origText.trim();

  // Nạp text đơn vào ô Nhanh 1 LẦN khi đơn về — không đè khi reload nền
  useEffect(() => {
    if (detail && !seededText.current) { seededText.current = true; setText(origText); }
  }, [detail]);

  // Tab Nâng cao bước 1: kéo nợ + tên bảng giá của khách hiện tại (cùng đường với
  // trang tạo đơn — previewOrder text rỗng trả customer đầy đủ, rồi kéo nợ KV MỚI).
  useEffect(() => {
    if (!custKey) { setCust(null); return; }
    let alive = true;
    previewOrder("", custKey)
      .then((r) => { if (alive) setCust(r.customer); })
      .catch(() => {});
    return () => { alive = false; };
  }, [custKey]);
  useEffect(() => {
    const id = cust?.id;
    if (!id) return;
    let alive = true;
    refreshCustomerDebt(id)
      .then((c) => { if (alive) setCust((p) => (p && p.id === id ? { ...p, debt: c.debt } : p)); })
      .catch(() => {});
    return () => { alive = false; };
  }, [cust?.id]);

  // Tab Nhanh: xem trước tức thời khi gõ. Text CHƯA sửa → preview theo khách hiện
  // tại (chưa lưu được thì khỏi doạ đổi khách). Text ĐÃ sửa → mô phỏng đúng fix:
  // nhận diện khách từ text trước, không nhận ra thì rơi về khách hiện tại (fix
  // giữ nguyên khách, giá vẫn theo bảng giá của họ). seq chặn kết quả cũ đè mới.
  useEffect(() => {
    const t = text.trim();
    if (!t) { seq.current++; setPreview(null); setPreviewing(false); return; }
    const changed = t !== origText.trim();
    const my = ++seq.current;
    setPreviewing(true);
    (async () => {
      try {
        let r;
        if (!changed && custKey) r = await previewOrder(t, custKey);
        else {
          r = await previewOrder(t);
          if (!r.customer && custKey && my === seq.current) r = await previewOrder(t, custKey);
        }
        if (my === seq.current) setPreview(r);
      } catch { if (my === seq.current) setPreview(null); }
      finally { if (my === seq.current) setPreviewing(false); }
    })();
  }, [text, custKey, origText]);

  // Khách trong preview → kéo nợ MỚI từ KiotViet 1 lần (theo id, không mỗi phím)
  useEffect(() => {
    const id = preview?.customer?.id;
    if (!id) { setLiveDebt(null); return; }
    let alive = true;
    refreshCustomerDebt(id)
      .then((c) => { if (alive) setLiveDebt({ id, debt: c.debt }); })
      .catch(() => {});
    return () => { alive = false; };
  }, [preview?.customer?.id]);

  // Giữ khoá "1 người sửa hoá đơn" khi trang mở (cả 2 tab đều sửa hoá đơn):
  // heartbeat 20s, nhả khi rời trang. Người khác giữ (mine=false) → banner + poll
  // nhanh 4s để bắt lúc họ nhả rồi tự vào sửa.
  useEffect(() => {
    if (!editable) return;
    let alive = true; let t: any;
    const beat = async () => {
      let blocked = false;
      try {
        const r = await lockInvoiceEdit(threadId);
        blocked = !!(r && r.mine === false);
        if (alive) setEditHolder(blocked ? r.holder : null);
      } catch { /* im lặng — thử lại nhịp sau */ }
      if (alive) t = setTimeout(beat, blocked ? 4000 : 20000);
    };
    beat();
    return () => { alive = false; clearTimeout(t); unlockInvoiceEdit(threadId).catch(() => {}); };
  }, [editable, threadId]);

  // Thay entry "Sửa hoá đơn" bằng trang chi tiết. Nếu chỉ gán location.hash,
  // trình duyệt sẽ thêm một entry mới và nút Back sẽ mở lại form vừa rời.
  const goBack = () => { window.location.replace(`#/order/${threadId}`); };

  // Lưu tab Nhanh — /api/order/fix: server parse lại khách + SP từ text (async)
  const saveQuick = async () => {
    if (!text.trim() || !textChanged) return;
    setBusy(true);
    try {
      await postJSON("/api/order/fix", { thread_id: Number(threadId), text: text.trim() });
      invalidateListCache();
      toast("✅ Đã lưu — đang nhận diện lại khách + SP", "ok");
      goBack();
    } catch (ex: any) { toast(`❌ ${ex.message}`, "err"); } finally { setBusy(false); }
  };

  // Lưu tab Nâng cao — /api/order/invoice/update: ghi thẳng dòng SP/CK/PVC/VAT
  const saveInvoice = async (payload: EditorPayload) => {
    await postJSON("/api/order/invoice/update", { thread_id: Number(threadId), ...payload });
    invalidateListCache();
    toast("✅ Đã lưu hoá đơn", "ok");
    goBack();
  };

  // Đổi/gán khách (bước 1 Nâng cao) — lưu ngay; custKey đổi → InvoiceEditor tự tra
  // lại giá bảng theo khách mới, dòng SP đang sửa GIỮ NGUYÊN; preview Nhanh cũng theo.
  const assignCustomer = async (c: { key: string; name: string } | null) => {
    if (!c) return;
    try {
      await postJSON("/api/order/assign-customer", { thread_id: Number(threadId), customer_key: c.key });
      setChangingCust(false);
      setDetail((p: any) => (p ? { ...p, data: { ...p.data, khach_hang_id: c.key, customer_name: c.name } } : p));
      invalidateListCache();
      toast(`✅ Đã gán khách: ${c.name}`, "ok");
    } catch (ex: any) { toast(`❌ ${ex.message}`, "err"); }
  };

  // Khối khách trong preview Nhanh: khách nhận từ text (kèm cảnh báo nếu KHÁC khách
  // hiện tại — lưu sẽ đổi), hoặc khách hiện tại khi text không nêu ai.
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
    const isCurrent = String(c.id) === String(custKey);
    const isLive = liveDebt?.id === c.id;
    const debt = isLive ? liveDebt!.debt : c.debt;
    return (
      <>
        <div class="co-prev-cust">
          <a class="co-cust-link" href={`#/khach/${encodeURIComponent(c.id)}`}>
            <span class="co-avatar" aria-hidden="true">{initial(c.name || "?")}</span>
            <div class="co-prev-cinfo">
              <span class="co-cust-line"><b>{c.name}</b><Icon name="chevronRight" size={14} class="co-cust-chev" /></span>
              <span class="muted small">
                {c.manual ? "Khách hiện tại của đơn" : isCurrent ? `Khớp ${c.score}% · khách hiện tại` : `Khớp ${c.score}%`}
              </span>
            </div>
          </a>
          {debt != null && <span class={"co-debt" + (debt > 0 ? " owe" : "")}>Nợ {money(debt)}{isLive ? " 🟢" : ""}</span>}
        </div>
        {!c.manual && !isCurrent && custKey && (
          <p class="err-msg small">⚠ Lưu sẽ ĐỔI khách của đơn: {custName || "khách hiện tại"} → <b>{c.name}</b></p>
        )}
      </>
    );
  };

  if (err) return <ErrorState msg={err} onRetry={reload} />;
  if (!detail) return <Loading />;

  // Đơn khoá / người khác đang sửa → chỉ xem: text + banner, không tab
  if (locked || editHolder) {
    return (
      <div>
        <div class="prod-detail-head">
          <BackLink fallback={`#/order/${threadId}`} />
          <div><div class="prod-sp big">Sửa hoá đơn · đơn #{threadId}</div></div>
        </div>
        <div class="card">
          <div class="ie-head">Nội dung đơn hàng</div>
          <pre class="order-text">{origText || "(trống)"}</pre>
        </div>
        <div class="card co-adv-locked muted small">
          <Icon name="lock" size={14} />{" "}
          {hasInvoice
            ? <>Đơn đã tạo hoá đơn KiotViet ({j.kiotvietInvoiceCode || j.kiotvietInvoiceID}) — không sửa được. Muốn sửa phải xoá HĐ ở trang chi tiết trước.</>
            : stockLocked
            ? <>Đơn đã <b>chốt xuất kho</b> — không sửa hoá đơn được. Admin bấm <b>Huỷ chốt</b> ở khối Xuất kho mới sửa được.</>
            : <><b>{editHolder}</b> đang sửa hoá đơn đơn này — chờ họ xong. Trang sẽ tự mở cho bạn khi họ rời.</>}
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Header + chọn tab — giấu khi đang gõ để nhường chỗ cho 2 cột chia đôi */}
      {!typing && (
        <>
          <div class="prod-detail-head">
            <BackLink fallback={`#/order/${threadId}`} />
            <div><div class="prod-sp big">Sửa hoá đơn · đơn #{threadId}</div></div>
          </div>
          <div class="seg" role="tablist">
            <button class={mode === "quick" ? "seg-btn active" : "seg-btn"} onClick={() => setMode("quick")}>
              <Icon name="zap" size={15} /> Nhanh
            </button>
            <button class={mode === "advanced" ? "seg-btn active" : "seg-btn"} onClick={() => setMode("advanced")}>
              <Icon name="clipboard" size={15} /> Nâng cao
            </button>
          </div>
        </>
      )}

      {/* TAB NHANH — sửa text đơn + xem trước (layout chia đôi khi gõ, như trang tạo) */}
      <div style={mode === "quick" ? undefined : "display:none"} class={typing ? "co-typing" : undefined}>
        <div class="co-split" onClick={typing ? exitTypingOnOutsideTap : undefined}>
          {text.trim() !== "" && (
            <div class="co-preview">
              <div class="co-prev-head">
                <Icon name="eye" size={13} /> Xem trước
                {previewing && <span class="co-spin" aria-label="đang phân tích" />}
                {textChanged && (
                  <button class="co-prev-go" disabled={busy} onClick={saveQuick}>
                    {busy ? "Đang lưu…" : "Lưu ▸"}
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
                            <td>{it.sp} <span class="co-pmini">·{moneyK(it.price)}</span></td>
                            <td class="num">x{it.sl}</td>
                            <td class="num">
                              {money(it.price)}
                              {it.list_price != null && it.list_price > 0 && it.list_price !== it.price && (
                                <div class="old-price">{money(it.list_price)}</div>
                              )}
                            </td>
                            <td class="num"><b>{money(it.sub)}</b></td>
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
                      <b>{money(preview.total)}</b>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          <textarea ref={taRef} class="co-input" placeholder="Text đơn trống — gõ như tạo đơn mới…" value={text}
            onFocus={() => setTyping(true)} onBlur={() => setTyping(false)}
            onInput={(e: any) => setText(e.target.value)} />
        </div>

        <button class="btn primary wide co-submit" disabled={busy || !text.trim() || !textChanged} onClick={saveQuick}>
          {busy ? "Đang lưu…" : textChanged ? "Lưu — nhận diện lại khách + SP" : "Sửa text rồi bấm Lưu"}
        </button>
        <p class="co-note muted small">
          💡 Lưu tab Nhanh = phân tích lại từ text như lúc tạo đơn: khách nhận theo text,
          giá tính lại theo bảng giá (giá đã sửa tay sẽ bị tính lại). Muốn chỉnh từng dòng/giá → tab Nâng cao.
        </p>
      </div>

      {/* TAB NÂNG CAO — 2 bước như trang tạo: khách hàng → sản phẩm (giá theo khách) */}
      <div style={mode === "advanced" ? undefined : "display:none"} class="co-adv">
        <div class="card co-adv-step">
          <div class="co-step-head"><span class="co-step-n">1</span> Khách hàng</div>
          {custKey && !changingCust ? (
            <div class="co-cust-picked adv">
              <span class="co-avatar" aria-hidden="true">{initial(custName || cust?.name || "?")}</span>
              <div class="co-prev-cinfo">
                <b>{custName || cust?.name || custKey}</b>
                <span class="muted small">
                  {cust?.price_list_name
                    ? <>Bảng giá: {cust.price_list_name}{" "}
                        <button class="co-link" onClick={() => setPlCust(cust!.id)}>Xem giá</button></>
                    : "Giá chung"}
                </span>
              </div>
              {cust?.debt != null && (
                <span class={"co-debt" + (cust.debt > 0 ? " owe" : "")}>Nợ {money(cust.debt)}</span>
              )}
              {canChange && <button class="btn small ghost" onClick={() => setChangingCust(true)}>Đổi</button>}
            </div>
          ) : (
            <>
              <CustomerPicker onPick={assignCustomer} placeholder={custKey ? "Tìm khách mới…" : "Gán khách cho đơn…"} />
              {changingCust
                ? <button class="btn small ghost" style="margin-top:8px" onClick={() => setChangingCust(false)}>Huỷ đổi khách</button>
                : <p class="muted small">Chưa gán khách — giá sẽ không tự lấy theo bảng giá.</p>}
            </>
          )}
        </div>

        <div class="co-step-head outside"><span class="co-step-n">2</span> Sản phẩm &amp; hoá đơn</div>
        <InvoiceEditor
          customerId={custKey || undefined}
          invoice={j.invoice || []}
          discount={j.discount}
          pvc={j.pvc}
          vat={j.vat}
          onSave={saveInvoice}
          onCancel={goBack}
        />
      </div>

      {plCust && <PriceListModal customerId={plCust} onClose={() => setPlCust(null)} />}
    </div>
  );
}
