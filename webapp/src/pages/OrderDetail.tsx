// Chi tiết đơn — header + text + ghép các khối detail/* (tasks, invoice,
// payments, comments). Data: GET /api/order/{thread_id}. In: POST /api/order/print-giao.
import { useEffect, useRef, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { createKiotVietInvoice, currentUser, deleteKiotVietInvoice, getCustomerOrders, getJSON, invoiceHtmlUrl, listOrderImages, orderImageUrl, postJSON, refreshOrderDebt, setOrderNgayGiao } from "../api";
import { onRealtime } from "../realtime";
import { money, invoiceTotal, paidTotal, fmtNgayGiao, fmtDateTimeVN, fmtRelative } from "../format";
import { Comments } from "../detail/Comments";
import { InvoiceEditor, type EditorPayload } from "../detail/InvoiceEditor";
import { CustomerPicker } from "../detail/CustomerPicker";
import { Payments } from "../detail/Payments";
import { Tasks } from "../detail/Tasks";
import { History } from "../detail/History";
import { Images } from "../detail/Images";
import { ImageStrip } from "../detail/ImageStrip";
import { OrderStock } from "../detail/OrderStock";
import { invalidateListCache, markLastOrder, filterNeighbors } from "./OrdersList";
import { confirmDialog, toast } from "../ui/feedback";
import { Loading, ErrorState } from "../ui/states";
import { fastScrollToEl, fastScrollTop } from "../scroll";
import { Icon } from "../ui/Icon";

export function OrderDetail({ threadId, focus }: { threadId: string; focus?: string }) {
  const [detail, setDetail] = useState<any>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [editText, setEditText] = useState<string | null>(null);
  const [changingCust, setChangingCust] = useState(false);
  const [nggDate, setNggDate] = useState("");   // ngày giao (YYYY-MM-DD)
  const [nggTime, setNggTime] = useState("");   // giờ giao (HH:MM) — tách riêng
  const [savingNg, setSavingNg] = useState(false);
  const [camSignal, setCamSignal] = useState(0);   // tăng để mở camera ở khối Ảnh
  const [custIds, setCustIds] = useState<number[]>([]);   // thread_id mọi đơn cùng khách (mới→cũ)
  const [showBar, setShowBar] = useState(false);          // hiện thanh dính (cuộn qua 5 icon)
  const statusRef = useRef<HTMLDivElement>(null);         // 5 icon trạng thái — mốc quan sát
  const seenTs = useRef<string | null>(null); // ts mới nhất đã báo — chặn báo lại lịch sử cũ
  const saveTimer = useRef<any>(null);
  useEffect(() => () => clearTimeout(saveTimer.current), []); // huỷ timer "sửa text" khi unmount

  const reload = async () => {
    try {
      setDetail(await getJSON(`/api/order/${threadId}`));
      setErr("");
    } catch (ex: any) {
      setErr(ex.message);
    }
  };
  // Sau khi SỬA đơn: xoá cache dashboard rồi tải lại (đơn có thể đã rời filter)
  const changed = () => { invalidateListCache(); reload(); };

  // Seed 2 input ngày/giờ giao từ đơn. Giờ 00:00 = "chưa đặt giờ" → ô giờ để trống.
  useEffect(() => {
    const v = detail?.data?.ngay_giao || "";
    setNggDate(v.slice(0, 10));
    const t = v.slice(11, 16);
    setNggTime(t && t !== "00:00" ? t : "");
  }, [detail?.data?.ngay_giao]);
  // Ghép lại: có giờ → 'YYYY-MM-DDTHH:MM', chỉ ngày → 'YYYY-MM-DD', không ngày → ''.
  const nggCombined = nggDate ? (nggTime ? `${nggDate}T${nggTime}` : nggDate) : "";
  // Tự lưu ngay khi đổi ngày/giờ (không cần nút Lưu) — tính combined từ giá trị MỚI.
  const commitNgg = async (d: string, t: string) => {
    setSavingNg(true); setMsg("");
    try { await setOrderNgayGiao(threadId, d ? (t ? `${d}T${t}` : d) : ""); changed(); setMsg("✅ Đã lưu ngày giao"); }
    catch (e: any) { setMsg(`❌ ${e.message}`); }
    finally { setSavingNg(false); }
  };
  useEffect(() => {
    markLastOrder(threadId); // ghi nhận đơn vừa mở → dashboard tô sáng khi quay lại
    reload();
  }, [threadId]);

  // Tải danh sách đơn CÙNG KHÁCH (mọi trang) cho thanh điều hướng ⏮/⏭ — chỉ khi có khách
  const custKey = detail?.data?.khach_hang_id;
  useEffect(() => {
    if (!custKey) { setCustIds([]); return; }
    let alive = true;
    (async () => {
      const ids: number[] = [];
      let page = 1, pages = 1;
      do {
        try {
          const d = await getCustomerOrders(String(custKey), page);
          ids.push(...(d.orders || []).map((o: any) => o.thread_id));
          pages = d.total_pages || 1;
        } catch { break; }
        page++;
      } while (page <= pages && page <= 10);
      if (alive) setCustIds(ids);
    })();
    return () => { alive = false; };
  }, [custKey]);

  // (Vị trí cuộn do hệ trung tâm ở main.tsx quản: mở đơn = forward → lên đầu;
  //  quay lại danh sách = back → khôi phục. Deep-link ?focus xử lý riêng bên dưới.)

  // Deep-link notification: đợi phần tử (bình luận/ảnh) render rồi cuộn tới + nháy sáng.
  // Ảnh nằm CUỐI trang; Bình luận/Lịch sử ở trên tải bất đồng bộ SAU khi đã cuộn →
  // đẩy vị trí trôi đi. Nên cuộn lại nhiều lần trong ~1.6s để bám đúng vị trí.
  useEffect(() => {
    if (!focus) return;
    let tries = 0;
    let flashT: any, settleIv: any;
    const iv = setInterval(() => {
      const el = document.getElementById(focus);
      if (el) {
        clearInterval(iv);
        fastScrollToEl(el, "center");
        el.classList.add("flash-target");
        flashT = setTimeout(() => el.classList.remove("flash-target"), 2400);
        history.replaceState(null, "", `#/order/${threadId}`); // xoá ?focus khỏi URL
        // Cuộn lại vài lần để chống trôi khi nội dung phía trên (bình luận/lịch sử) vừa tải xong
        let n = 0;
        settleIv = setInterval(() => {
          const e2 = document.getElementById(focus);
          if (e2) fastScrollToEl(e2, "center");
          if (++n >= 5 || !e2) clearInterval(settleIv);
        }, 320);
      } else if (++tries > 50) {
        clearInterval(iv); // ~5s không thấy → thôi
      }
    }, 100);
    return () => { clearInterval(iv); clearInterval(settleIv); clearTimeout(flashT); };
  }, [focus, threadId]);

  // Realtime: đơn này đổi (task/thanh toán/bình luận…) hoặc vừa nối lại → tải lại.
  // Gộp event dồn dập bằng debounce nhỏ. editText giữ nguyên (state riêng, reload
  // chỉ thay detail nền) nên không phá thao tác sửa đang mở.
  // Baseline: ghi nhận ts thao tác mới nhất khi mở đơn (không popup lịch sử cũ)
  useEffect(() => {
    seenTs.current = null;
    getJSON(`/api/order/${threadId}/history`, { cache: false })
      .then((r) => { seenTs.current = (r.history || [])[0]?.ts || null; })
      .catch(() => {});
  }, [threadId]);

  useEffect(() => {
    let t: any, tt: any;
    const line = (h: any) => `• ${h.actor || "?"}: ${h.action}${h.detail ? ` — ${h.detail}` : ""}`;
    const off = onRealtime((e) => {
      if (e.type === "resync") {
        clearTimeout(t); t = setTimeout(reload, 250);
        return;
      }
      if (e.type === "order_changed" && e.thread_id === String(threadId)) {
        clearTimeout(t); t = setTimeout(reload, 250);
        // Gom mọi thao tác đến trong 1 đợt ngắn (debounce), popup 1 lần
        clearTimeout(tt);
        tt = setTimeout(async () => {
          try {
            const r = await getJSON(`/api/order/${threadId}/history`, { cache: false });
            const all = r.history || [];
            // các thao tác mới hơn ts đã thấy (history sắp mới→cũ)
            const fresh = seenTs.current ? all.filter((h: any) => h.ts > seenTs.current!) : all.slice(0, 1);
            if (!fresh.length) return;
            seenTs.current = all[0].ts;
            const msg = fresh.length === 1
              ? `🔔 ${fresh[0].actor || "?"}: ${fresh[0].action}${fresh[0].detail ? ` — ${fresh[0].detail}` : ""}`
              : [`🔔 ${fresh.length} thao tác mới`, ...fresh.slice(0, 4).map(line), fresh.length > 4 ? `… +${fresh.length - 4} nữa` : ""].filter(Boolean).join("\n");
            toast(msg, "info");
          } catch { /* ignore */ }
        }, 600);
      }
    });
    return () => { off(); clearTimeout(t); clearTimeout(tt); };
  }, [threadId]);

  // Cuộn qua 5 icon trạng thái → hiện thanh dính tóm tắt ở đỉnh
  useEffect(() => {
    const el = statusRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([e]) => setShowBar(!e.isIntersecting && e.boundingClientRect.top < 80),
      { rootMargin: "-76px 0px 0px 0px", threshold: 0 },  // app-bar 44 + header dính ~32
    );
    io.observe(el);
    return () => io.disconnect();
  }, [detail]);

  if (err && !detail) return <ErrorState msg={err} onRetry={reload} />;
  if (!detail) return <Loading />;

  const j = detail.data || {};
  const pc = (j.hoadon || {}).print_content || {};
  const isAdmin = currentUser()?.role === "admin";
  // ưu tiên tổng từ hoá đơn in (đã gồm mọi điều chỉnh); tự tính thì phải cộng trừ
  // discount/pvc/vat như /api/order/totals — không thì lệch với Telegram
  const computedTotal = invoiceTotal(j.invoice) - (Number(j.discount) || 0) + (Number(j.pvc) || 0) + (Number(j.vat) || 0);
  const total = pc.tongthanhtoan ? pc.tongthanhtoan : money(computedTotal);
  const paid = paidTotal(j.payments);
  const remaining = Math.max(0, computedTotal - paid);
  const hasInvoice = !!j.kiotvietInvoiceID;

  // Điều hướng đơn↔đơn: liền kề trong DANH SÁCH lọc + liền kề CÙNG KHÁCH (mới→cũ)
  const fil = filterNeighbors(threadId);
  const ci = custIds.findIndex((id) => String(id) === String(threadId));
  const custPrev = ci > 0 ? custIds[ci - 1] : null;
  const custNext = ci >= 0 && ci < custIds.length - 1 ? custIds[ci + 1] : null;
  const gotoOrder = (id: number | null) => { if (id) window.location.hash = `#/order/${id}`; };

  // 5 icon trạng thái (khớp renderers.order_parts.status_icons / main message Telegram)
  const TASK_STEPS: [string, string][] = [["ban_hd", "Bán HĐ"], ["soan_hang", "Soạn"], ["giao_hang", "Giao"], ["nop_tien", "Nộp"], ["nhan_tien", "Nhận"]];
  const stepIcon = (tt: string, st: any): string => {
    const note = String(st?.note || "").toLowerCase();
    if (tt === "nhan_tien" && st?.done && note === "gtr") return "📄";
    if (tt === "nop_tien" && !st?.done && note === "chieu_lay_tien") return "🟨";
    if (st?.done && st?.skip) return "🔘";
    if (st?.done) return "✅";
    return "❌";
  };
  const ts = j.task_status || {};

  // Điều hướng nhanh trong trang — cuộn NHANH dùng chung + nháy sáng mục đích
  const scrollTo = (id: string) => {
    const el = document.getElementById(id);
    if (!el) return;
    fastScrollToEl(el, "center");
    el.classList.remove("flash-target");
    void el.offsetWidth;               // reflow → chạy lại animation nếu bấm liên tiếp
    el.classList.add("flash-target");
    setTimeout(() => el.classList.remove("flash-target"), 2400);
  };
  const goCamera = () => { scrollTo("od-camera"); setCamSignal((s) => s + 1); };  // cuộn + mở camera
  const goInvoice = () => scrollTo("od-invoice");
  const goPay = () => scrollTo("od-payments");
  const goTasks = () => scrollTo("od-tasks");
  const goImages = () => scrollTo("od-camera");
  const goStock = () => scrollTo("od-stock");
  const goChat = () => scrollTo("od-chat");

  // URL ảnh PNG hoá đơn trong gallery (kind hoa_don, hoặc ảnh cũ uploaded_by
  // "KiotViet HĐ"); null nếu chưa render / chưa tạo HĐ.
  const findInvoiceImageUrl = async (): Promise<string | null> => {
    try {
      const imgs = await listOrderImages(threadId);
      const inv = imgs.find((x) => x.kind === "hoa_don" || x.uploaded_by === "KiotViet HĐ");
      return inv ? orderImageUrl(threadId, inv.id, "full") : null;
    } catch { return null; }
  };

  const doPrint = async () => {
    const imgUrl = await findInvoiceImageUrl();   // xem lại hoá đơn trước khi in
    if (!(await confirmDialog("In 2 hoá đơn + phiếu giao?", { okLabel: "In", imageUrl: imgUrl || undefined }))) return;
    setBusy(true);
    try {
      const r = await postJSON("/api/order/print-giao", { thread_id: Number(threadId) });
      setMsg(r.error ? `❌ ${r.error}` : "🖨️ Đã gửi lệnh in");
    } catch (ex: any) {
      setMsg(`❌ ${ex.message}`);
    } finally {
      setBusy(false);
    }
  };

  const assignCustomer = async (c: { key: string; name: string } | null) => {
    if (!c) return;
    try {
      await postJSON("/api/order/assign-customer", { thread_id: Number(threadId), customer_key: c.key });
      setMsg(`✅ Đã gán khách: ${c.name}`);
      setChangingCust(false);
      changed();
    } catch (ex: any) {
      setMsg(`❌ ${ex.message}`);
    }
  };

  const saveInvoice = async (payload: EditorPayload) => {
    await postJSON("/api/order/invoice/update", { thread_id: Number(threadId), ...payload });
    setMsg("✅ Đã lưu hoá đơn");
    changed();
  };

  const createHD = async () => {
    if (!(await confirmDialog("Tạo hoá đơn KiotViet cho đơn này?"))) return;
    try {
      const r = await createKiotVietInvoice(threadId);
      setMsg(`🧾 Đã tạo HĐ ${r.kv_code || ""}${r.old_debt ? ` · nợ cũ ${money(r.old_debt)}đ` : ""}`);
      changed();
    } catch (ex: any) {
      setMsg(`❌ ${ex.message}`);
    }
  };

  const refreshDebt = async () => {
    try {
      const r = await refreshOrderDebt(threadId);
      setMsg(`💰 Đã cập nhật nợ KiotViet: ${money(r.debt)}đ`);
      changed();
    } catch (ex: any) {
      setMsg(`❌ ${ex.message}`);
    }
  };

  const deleteHD = async () => {
    if (!(await confirmDialog("XOÁ hoá đơn KiotViet của đơn này? Không thể hoàn tác.", { danger: true }))) return;
    try {
      await deleteKiotVietInvoice(threadId);
      setMsg("🗑️ Đã xoá hoá đơn KiotViet");
      changed();
    } catch (ex: any) {
      setMsg(`❌ ${ex.message}`);
    }
  };

  const saveText = async () => {
    if (editText === null) return;
    setBusy(true);
    try {
      await postJSON("/api/order/fix", { thread_id: Number(threadId), text: editText });
      setMsg("✅ Đã sửa text — hệ thống đang parse lại");
      setEditText(null);
      saveTimer.current = setTimeout(changed, 1500);
    } catch (ex: any) {
      setMsg(`❌ ${ex.message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div class="detail">
      {/* Header DÍNH: bình thường = back + mã đơn; cuộn qua 5 icon → gộp thành
          back + 5 icon + nội dung đơn (rút gọn). Bấm vào phần tóm tắt = lên đầu. */}
      <header class={"od-appbar" + (showBar ? " summary" : "")}>
        <BackLink fallback="#/orders" className="od-back" />
        {showBar ? (
          <div class="od-summary" onClick={() => fastScrollTop()} title="Lên đầu">
            <div class="od-sb-status">
              {TASK_STEPS.map(([tt, lbl]) => (
                <button class="od-sb-ic" key={tt} onClick={(e: any) => { e.stopPropagation(); scrollTo(`task-${tt}`); }} title={lbl}>
                  {stepIcon(tt, ts[tt] || {})}
                </button>
              ))}
            </div>
            <div class="od-sb-text" title={j.text || j.text_raw || ""}>{j.text || j.text_raw || `#${threadId}`}</div>
          </div>
        ) : (
          <div class="od-appttl">Đơn <span class="od-id">#{threadId}</span></div>
        )}
      </header>
      {detail._stale && <p class="muted small">⚠️ Dữ liệu lưu sẵn (mất mạng)</p>}
      {msg && <p class="notice" onClick={() => setMsg("")}>{msg}</p>}

      <div class="detail-grid">
      <div class="dmain">
      <div class="card">
        <div class="row space">
          <b>Nội dung đơn</b>
          {editText === null && <button class="btn small" onClick={() => setEditText(j.text || j.text_raw || "")}>Sửa</button>}
        </div>
        {editText === null ? (
          <>
            <pre class="order-text">{j.text || j.text_raw || "(trống)"}</pre>
            {j.created && <div class="muted small od-created"><Icon name="clock" size={13} /> Tạo lúc {fmtDateTimeVN(j.created)} · {fmtRelative(j.created)}</div>}
          </>
        ) : (
          <div>
            <textarea rows={6} value={editText} onInput={(e: any) => setEditText(e.target.value)} />
            <div class="row">
              <button class="btn primary" disabled={busy} onClick={saveText}>Lưu & parse lại</button>
              <button class="btn" onClick={() => setEditText(null)}>Huỷ</button>
            </div>
          </div>
        )}
      </div>

      {/* 5 icon trạng thái (như main message Telegram) — trên Thao tác nhanh */}
      <div class="od-status" ref={statusRef}>
        {TASK_STEPS.map(([tt, lbl]) => (
          <button class="ods-cell" key={tt} onClick={() => scrollTo(`task-${tt}`)} title={`Tới bước ${lbl} ở Tiến độ`}>
            <span class="ods-ic">{stepIcon(tt, ts[tt] || {})}</span>
            <span class="ods-lb">{lbl}</span>
          </button>
        ))}
      </div>

      {/* Thao tác nhanh — nút vuông nhảy tới các mục hay dùng, khỏi cuộn tìm */}
      <div class="card od-quick">
        <b class="od-quick-ttl">Thao tác nhanh</b>
        <div class="qa-grid">
          <button class="qa" onClick={goCamera}><Icon name="camera" size={22} class="qa-ic" /><span class="qa-lb">Chụp ảnh</span></button>
          <button class={"qa" + (hasInvoice ? "" : " qa-off")} disabled={busy}
            onClick={hasInvoice ? doPrint : () => toast("Chưa có hoá đơn để in", "info")}>
            <Icon name="printer" size={22} class="qa-ic" /><span class="qa-lb">In hoá đơn</span>
          </button>
          <button class="qa" onClick={goInvoice}><Icon name="receipt" size={22} class="qa-ic" /><span class="qa-lb">Hoá đơn</span></button>
          <button class="qa" onClick={goPay}><Icon name="wallet" size={22} class="qa-ic" /><span class="qa-lb">Thanh toán</span></button>
          <button class="qa" onClick={goTasks}><Icon name="check" size={22} class="qa-ic" /><span class="qa-lb">Tiến độ</span></button>
          <button class="qa" onClick={goStock}><Icon name="box" size={22} class="qa-ic" /><span class="qa-lb">Xuất kho</span></button>
          <button class="qa" onClick={goChat}><Icon name="chat" size={22} class="qa-ic" /><span class="qa-lb">Trao đổi</span></button>
          <button class="qa" onClick={goImages}><Icon name="image" size={22} class="qa-ic" /><span class="qa-lb">Ảnh</span></button>
        </div>
      </div>

      {/* Xem trước ảnh — bấm thumb mở lightbox; ô 📸 cuối cùng để chụp/thêm */}
      <ImageStrip base={`/api/order/${threadId}`} onCamera={goCamera} />

      <div class="card">
        <div class="row space">
          <span>Khách hàng</span>
          {(j.customer_name || j.khach_hang_id) && !changingCust && (
            <button class="btn small" onClick={() => setChangingCust(true)}>Đổi</button>
          )}
        </div>
        {(j.customer_name || j.khach_hang_id) && !changingCust ? (
          j.khach_hang_id ? (
            <a class="cust-link" href={`#/khach/${encodeURIComponent(j.khach_hang_id)}`}>
              <b>{j.customer_name || pc.kh}</b> <span class="cust-link-arrow">›</span>
            </a>
          ) : (
            <b>{j.customer_name || pc.kh}</b>
          )
        ) : (
          <div>
            {!(j.customer_name || j.khach_hang_id) && <p class="muted small">⚠️ Đơn chưa có khách — tìm và gán để lấy giá + tạo HĐ.</p>}
            <CustomerPicker onPick={assignCustomer} placeholder="Tìm khách để gán" />
            {changingCust && <button class="btn small" onClick={() => setChangingCust(false)}>Huỷ</button>}
          </div>
        )}
      </div>

      <div class="card">
        <div class="row space">
          <b><Icon name="truck" size={16} /> Ngày giao</b>
          {j.ngay_giao && j.ngay_giao_auto ? <span class="muted small">tự đặt khi tạo đơn</span> : null}
        </div>
        <div class="row ngg-row">
          <input type="date" class="ngg-date" value={nggDate} disabled={savingNg}
            onChange={(e: any) => { const v = e.target.value; setNggDate(v); commitNgg(v, nggTime); }} />
          <input type="time" class="ngg-time" value={nggTime} disabled={!nggDate || savingNg}
            onChange={(e: any) => { const v = e.target.value; setNggTime(v); commitNgg(nggDate, v); }} />
          {savingNg && <span class="muted small">⏳</span>}
          {nggDate && !savingNg && <button class="btn small" title="Xoá ngày giao" onClick={() => { setNggDate(""); setNggTime(""); commitNgg("", ""); }}>✕</button>}
        </div>
        {nggCombined ? <p class="muted small">Giao dự kiến: <b>{fmtNgayGiao(nggCombined)}</b> · tự lưu khi đổi</p> : <p class="muted small">Chưa đặt ngày giao.</p>}
      </div>

      <div id="od-tasks">
      <Tasks threadId={threadId} taskStatus={j.task_status || {}} customTasks={j.custom_tasks || []} userNames={detail.user_names || {}} onChanged={changed} />
      </div>
      <div id="od-invoice">
      <InvoiceEditor
        customerId={j.khach_hang_id || j.khID}
        invoice={j.invoice || []}
        discount={j.discount}
        pvc={j.pvc}
        vat={j.vat}
        onSave={saveInvoice}
        onCreateInvoice={createHD}
        canCreate={isAdmin}
        hasInvoice={!!j.kiotvietInvoiceID}
        debt={j.khDebt ?? j.invoice_debt_snapshot}
        onView={async () => {
          // Mở ảnh PNG hoá đơn (đã render khi tạo HĐ); không có thì fallback HTML sống.
          const win = window.open("", "_blank");   // mở ngay trong user-gesture → khỏi bị chặn popup
          const go = (u: string) => { if (win) win.location.href = u; else window.open(u, "_blank"); };
          go((await findInvoiceImageUrl()) || invoiceHtmlUrl(threadId));
        }}
        onDelete={deleteHD}
        onPrint={doPrint}
        canDelete={isAdmin}
        invoiceCode={j.kiotvietInvoiceCode || j.kiotvietInvoiceID}
        onRefreshDebt={refreshDebt}
        debtLocked={!!j.kiotvietInvoiceID}
      />
      </div>{/* #od-invoice */}
      <div id="od-stock">
      <OrderStock threadId={threadId} invoice={j.invoice || []} />
      </div>
      <div id="od-payments">
      <Payments threadId={threadId} payments={j.payments || []} suggest={invoiceTotal(j.invoice)} onChanged={changed} />
      </div>
      <Images base={`/api/order/${threadId}`} anchorId="od-camera" openSignal={camSignal} />
      <History base={`/api/order/${threadId}`} />
      <div class="muted small center">Tạo bởi: {(j.nguoi_tao_HD || []).join(", ") || "?"} · thread {threadId}</div>
      </div>{/* .dmain */}

      <aside class="dside" id="od-chat">
        <Comments base={`/api/order/${threadId}`} chatMessages={detail.chat_messages || []} />
      </aside>
      </div>{/* .detail-grid */}

      {/* Thanh điều hướng đơn↔đơn (dính đáy): «« đơn trước KHÁCH · « đơn trước LỌC ·
          đơn sau LỌC » · đơn sau KHÁCH »» */}
      <div class="od-navbar">
        <button class="od-nav-btn" disabled={!custPrev} onClick={() => gotoOrder(custPrev)} title="Đơn trước của khách này">
          <span class="od-nav-ar">«</span><span class="od-nav-lb">khách</span>
        </button>
        <button class="od-nav-btn" disabled={!fil.prev} onClick={() => gotoOrder(fil.prev)} title="Đơn trước trong danh sách">
          <span class="od-nav-ar">‹</span><span class="od-nav-lb">lọc</span>
        </button>
        <button class="od-nav-btn" disabled={!fil.next} onClick={() => gotoOrder(fil.next)} title="Đơn sau trong danh sách">
          <span class="od-nav-ar">›</span><span class="od-nav-lb">lọc</span>
        </button>
        <button class="od-nav-btn" disabled={!custNext} onClick={() => gotoOrder(custNext)} title="Đơn sau của khách này">
          <span class="od-nav-ar">»</span><span class="od-nav-lb">khách</span>
        </button>
      </div>
    </div>
  );
}
