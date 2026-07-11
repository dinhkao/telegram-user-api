// Chi tiết đơn — header + text + ghép các khối detail/* (tasks, invoice,
// payments, comments). Data: GET /api/order/{thread_id}. In: POST /api/order/print-giao.
import { useEffect, useRef, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { createKiotVietInvoice, currentUser, deleteKiotVietInvoice, deleteOrder, ensureInvoiceImage, getCustomerOrders, getJSON, invoiceEditStatus, invoiceHtmlUrl, isOffice, listOrderImages, orderImageUrl, postJSON, refreshOrderDebt, setOrderNgayGiao, type OrderImage } from "../api";
import { onRealtime } from "../realtime";
import { money, initial, invoiceTotal, paidTotal, fmtNgayGiao, fmtDateTimeVN, fmtRelative } from "../format";
import { Comments } from "../detail/Comments";
import { InvoiceTable } from "../detail/InvoiceTable";
import { CustomerPicker } from "../detail/CustomerPicker";
import { Payments } from "../detail/Payments";
import { Tasks } from "../detail/Tasks";
import { History } from "../detail/History";
import { Images } from "../detail/Images";
import { ImageStrip } from "../detail/ImageStrip";
import { PhotoViewer } from "../detail/PhotoViewer";
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
  const [invEditBy, setInvEditBy] = useState<string | null>(null);   // ai đang sửa hoá đơn đơn này
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
    // User đụng vào (cuộn/chạm/phím) → thôi bám vị trí, trả quyền cuộn cho user
    let userTouched = false;
    const onUser = () => { userTouched = true; clearInterval(settleIv); };
    const evs: (keyof WindowEventMap)[] = ["wheel", "touchstart", "pointerdown", "keydown"];
    evs.forEach((ev) => window.addEventListener(ev, onUser, { passive: true }));
    const iv = setInterval(() => {
      const el = document.getElementById(focus);
      if (el) {
        clearInterval(iv);
        fastScrollToEl(el, "center");
        el.classList.add("flash-target");
        flashT = setTimeout(() => el.classList.remove("flash-target"), 2400);
        history.replaceState(null, "", `#/order/${threadId}`); // xoá ?focus khỏi URL
        // Chống trôi khi nội dung phía trên (bình luận/lịch sử) vừa tải xong:
        // CHỈ cuộn lại khi lệch thật (>8px) và user chưa đụng vào
        let n = 0;
        settleIv = setInterval(() => {
          const e2 = document.getElementById(focus);
          if (!e2 || userTouched || ++n > 5) return clearInterval(settleIv);
          const r = e2.getBoundingClientRect();
          const want = Math.max(56, (window.innerHeight - r.height) / 2);
          if (Math.abs(r.top - want) > 8) fastScrollToEl(e2, "center");
        }, 320);
      } else if (++tries > 50) {
        clearInterval(iv); // ~5s không thấy → thôi
      }
    }, 100);
    return () => {
      clearInterval(iv); clearInterval(settleIv); clearTimeout(flashT);
      evs.forEach((ev) => window.removeEventListener(ev, onUser));
    };
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

  // Lúc mở đơn: ai đang sửa hoá đơn (để làm mờ nút 'Sửa hoá đơn' ngay)
  useEffect(() => {
    setInvEditBy(null);
    invoiceEditStatus(threadId).then(setInvEditBy).catch(() => {});
  }, [threadId]);

  useEffect(() => {
    let t: any, tt: any;
    const line = (h: any) => `• ${h.actor || "?"}: ${h.action}${h.detail ? ` — ${h.detail}` : ""}`;
    const off = onRealtime((e) => {
      if (e.type === "resync" || e.type === "customer_changed") {
        clearTimeout(t); t = setTimeout(reload, 250);
        return;
      }
      if (e.type === "invoice_edit_lock" && e.thread_id === String(threadId)) {
        setInvEditBy(e.holder);   // ai đang sửa hoá đơn (null = nhả) → làm mờ/bỏ mờ nút
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
  const myName = currentUser()?.display_name || currentUser()?.username || "";
  const invLockedByOther = !!invEditBy && invEditBy !== myName;   // người khác đang sửa hoá đơn
  // ưu tiên tổng từ hoá đơn in (đã gồm mọi điều chỉnh); tự tính thì phải cộng trừ
  // discount/pvc/vat như /api/order/totals — không thì lệch với Telegram
  const computedTotal = invoiceTotal(j.invoice) - (Number(j.discount) || 0) + (Number(j.pvc) || 0) + (Number(j.vat) || 0);
  const total = pc.tongthanhtoan ? pc.tongthanhtoan : money(computedTotal);
  const paid = paidTotal(j.payments);
  const remaining = Math.max(0, computedTotal - paid);
  const hasInvoice = !!j.kiotvietInvoiceID;
  // Đổi/Gán khách bị KHOÁ khi đơn đã có HĐ KiotViet (HĐ tạo theo khách cũ) —
  // pattern nút khoá: mờ + toast lý do, server cũng chặn 400.
  const toggleCust = () => {
    if (hasInvoice) { toast("Đơn đã có hoá đơn KiotViet — không đổi khách được. Xoá hoá đơn trước.", "info"); return; }
    setChangingCust((v: boolean) => !v);
  };
  // Lý do khoá xoá đơn biết được từ blob (HĐ, thanh toán); phân bổ kho server chặn nốt
  const delOrderLock = hasInvoice
    ? "Còn HĐ KiotViet — xoá hoá đơn trước khi xoá đơn"
    : (j.payments?.length ? `Còn ${j.payments.length} thanh toán — xoá thanh toán trước khi xoá đơn` : "");
  const doDeleteOrder = async () => {
    if (delOrderLock) { toast(delOrderLock, "info"); return; }
    if (!(await confirmDialog(`Xoá đơn #${threadId}? Không thể hoàn tác.`, { danger: true, okLabel: "Xoá đơn" }))) return;
    try {
      await deleteOrder(threadId);
      invalidateListCache();
      toast("Đã xoá đơn", "ok");
      window.location.hash = "#/orders";
    } catch (e: any) {
      toast(e?.message || "Lỗi xoá đơn", "err");
    }
  };

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
  const hasDebt = !(j.payments || []).length;   // chưa có thanh toán nào = còn nợ → 😡

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

  // Thao tác HĐ KiotViet ngay tại khối Hoá đơn (trang Sửa hoá đơn bị khoá khi đã
  // có HĐ nên Tạo/Xem/Xoá phải có ở đây, như trước khi tách trang).
  const createHD = async () => {
    if (!(await confirmDialog("Tạo hoá đơn KiotViet cho đơn này?"))) return;
    setBusy(true);
    try {
      const r = await createKiotVietInvoice(threadId);
      setMsg(`🧾 Đã tạo HĐ ${r.kv_code || ""}${r.old_debt ? ` · nợ cũ ${money(r.old_debt)}` : ""}`);
      changed();
    } catch (ex: any) { setMsg(`❌ ${ex.message}`); } finally { setBusy(false); }
  };
  const deleteHD = async () => {
    if (!(await confirmDialog("XOÁ hoá đơn KiotViet của đơn này? Không thể hoàn tác.", { danger: true }))) return;
    setBusy(true);
    try { await deleteKiotVietInvoice(threadId); setMsg("🗑️ Đã xoá hoá đơn KiotViet"); changed(); }
    catch (ex: any) { setMsg(`❌ ${ex.message}`); } finally { setBusy(false); }
  };
  // Xem HĐ: mở ảnh hoá đơn trong PhotoViewer (zoom/pan như ảnh đơn);
  // chưa có ảnh → gọi server render PNG ngay rồi mở; lỗi mới fallback HTML tab.
  const [invViewer, setInvViewer] = useState<OrderImage | null>(null);
  const viewHD = async () => {
    try {
      const imgs = await listOrderImages(threadId);
      const inv = imgs.find((x) => x.kind === "hoa_don" || x.uploaded_by === "KiotViet HĐ");
      if (inv) { setInvViewer(inv); return; }
    } catch { /* thử render bên dưới */ }
    try {
      setMsg("⏳ Đang tạo ảnh hoá đơn…");
      const img = await ensureInvoiceImage(threadId);
      setMsg("");
      if (img) { setInvViewer(img); return; }
    } catch { setMsg(""); /* rơi xuống fallback */ }
    window.open(invoiceHtmlUrl(threadId), "_blank");
  };

  const refreshDebt = async () => {
    try { const r = await refreshOrderDebt(threadId); setMsg(`💰 Đã cập nhật nợ KiotViet: ${money(r.debt)}`); changed(); }
    catch (ex: any) { setMsg(`❌ ${ex.message}`); }
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

  // (Sửa/Tạo/Xoá/Kéo-nợ hoá đơn đã chuyển sang trang riêng: pages/OrderInvoiceEdit.)

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
              {hasDebt && (
                <button class="od-sb-ic" key="no" onClick={(e: any) => { e.stopPropagation(); scrollTo("od-payments"); }} title="Còn nợ — chưa có thanh toán">
                  😡
                </button>
              )}
            </div>
            <div class="od-sb-text" title={j.text || j.text_raw || ""}>{j.text || j.text_raw || `#${threadId}`}</div>
            {/* Khách — avatar bấm được (giữ ngữ cảnh khách khi cuộn); chạm = mở khách,
                không cuộn lên đầu. Chưa có khách thì bỏ. */}
            {j.khach_hang_id && (
              <a class="od-sb-cust" href={`#/khach/${encodeURIComponent(j.khach_hang_id)}`}
                onClick={(e: any) => e.stopPropagation()} title={j.customer_name || pc.kh || "Khách"}>
                <span class="co-avatar" aria-hidden="true">{initial(j.customer_name || pc.kh || "?")}</span>
              </a>
            )}
          </div>
        ) : (
          <>
            <div class="od-appttl">Đơn <span class="od-id">#{threadId}</span></div>
            {/* Khách hàng — chip phải appbar, giống box khách ở Tạo đơn (avatar +
                tên + ›). Chưa có khách → nút Gán khách; Đổi/Gán mở hàng picker dưới. */}
            <div class="od-cust">
              {(j.customer_name || j.khach_hang_id) ? (
                <>
                  {j.khach_hang_id ? (
                    <a class="od-cust-chip" href={`#/khach/${encodeURIComponent(j.khach_hang_id)}`}>
                      <span class="co-avatar" aria-hidden="true">{initial(j.customer_name || pc.kh || "?")}</span>
                      <b class="od-cust-name">{j.customer_name || pc.kh}</b>
                      <Icon name="chevronRight" size={14} class="co-cust-chev" />
                    </a>
                  ) : (
                    <span class="od-cust-chip">
                      <span class="co-avatar" aria-hidden="true">{initial(j.customer_name || pc.kh || "?")}</span>
                      <b class="od-cust-name">{j.customer_name || pc.kh}</b>
                    </span>
                  )}
                  <button class={"btn small ghost od-cust-btn" + (hasInvoice ? " faded" : "")}
                    title={hasInvoice ? "Đã có HĐ KiotViet — không đổi khách được" : undefined}
                    onClick={toggleCust}>Đổi</button>
                </>
              ) : (
                <button class={"od-cust-add" + (hasInvoice ? " faded" : "")}
                  title={hasInvoice ? "Đã có HĐ KiotViet — không đổi khách được" : undefined}
                  onClick={toggleCust}>
                  <Icon name="user" size={15} /> Gán khách
                </button>
              )}
            </div>
          </>
        )}
      </header>
      {changingCust && (
        <div class="od-cust-pickrow">
          <CustomerPicker onPick={assignCustomer} placeholder="Tìm khách để gán" />
          <button class="btn small" onClick={() => setChangingCust(false)}>Huỷ</button>
        </div>
      )}
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
            {j.created && <div class="muted small od-created"><Icon name="clock" size={13} /> Tạo lúc {fmtDateTimeVN(j.created)} · {fmtRelative(j.created)}{j.created_by ? <> · bởi <b>{j.created_by}</b></> : null}</div>}
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
        {hasDebt && (
          <button class="ods-cell" key="no" onClick={() => scrollTo("od-payments")} title="Còn nợ — chưa có thanh toán nào">
            <span class="ods-ic">😡</span>
            <span class="ods-lb">Nợ</span>
          </button>
        )}
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
      <ImageStrip base={`/api/order/${threadId}`} />

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
      <Tasks threadId={threadId} taskStatus={j.task_status || {}} customTasks={j.custom_tasks || []} userNames={detail.user_names || {}} onChanged={changed} onAddPhoto={goCamera} />
      </div>
      <div id="od-invoice">
      <section class="card">
        <b>Hoá đơn ({(j.invoice || []).length} món){j.kiotvietInvoiceCode ? ` · HĐ ${j.kiotvietInvoiceCode}` : ""}</b>
        {(j.invoice || []).length > 0
          ? <InvoiceTable items={j.invoice} discount={j.discount} pvc={j.pvc} vat={j.vat}
              debt={j.khDebt ?? j.invoice_debt_snapshot} total={pc.tongthanhtoan || undefined}
              debtCtl={!hasInvoice && (j.khach_hang_id || j.khID)
                ? <button class="btn small" title="Kéo nợ KiotViet mới nhất" onClick={refreshDebt}><Icon name="refresh" size={14} /></button>
                : undefined} />
          : <div class="muted small">Chưa có sản phẩm.</div>}
        {/* Chưa có HĐ: Sửa (trang riêng, thuần sửa) + Tạo HĐ (văn phòng).
            Có HĐ: chốt — chỉ Xem/In (+ Xoá admin), không còn nút Sửa. */}
        {hasInvoice ? (
          <>
            <div class="row" style={{ marginTop: "8px" }}>
              <button class="btn" style={{ flex: 1 }} onClick={viewHD}><Icon name="eye" size={16} /> Xem HĐ</button>
              <button class="btn" style={{ flex: 1 }} disabled={busy} onClick={doPrint}><Icon name="printer" size={16} /> In</button>
              {isAdmin && <button class="btn danger" style={{ flex: 1 }} disabled={busy} onClick={deleteHD}><Icon name="trash" size={16} /> Xoá HĐ</button>}
            </div>
            <div class="muted small" style={{ marginTop: "6px" }}>🔒 Đã tạo HĐ KiotViet — muốn sửa sản phẩm phải xoá HĐ trước.</div>
          </>
        ) : (
          <>
            <button class={"btn block primary" + (j.stock_confirmed || invLockedByOther ? " faded" : "")} style={{ marginTop: "8px" }}
              onClick={() => j.stock_confirmed
                ? toast("Đã chốt xuất kho — admin huỷ chốt mới sửa được số lượng/SP", "info")
                : invLockedByOther
                ? toast(`${invEditBy} đang sửa hoá đơn — chờ họ xong`, "info")
                : (window.location.hash = `#/order/${threadId}/hoa-don`)}>
              <Icon name="edit" size={16} /> {invLockedByOther ? `${invEditBy} đang sửa…` : "Sửa hoá đơn"}
            </button>
            {isOffice() && (j.invoice || []).length > 0 && (
              <button class="btn block" style={{ marginTop: "8px" }} disabled={busy} onClick={createHD}>
                <Icon name="receipt" size={16} /> {busy ? "Đang tạo…" : "Tạo HĐ KiotViet"}
              </button>
            )}
          </>
        )}
        {invViewer && (
          <PhotoViewer images={[invViewer]} start={0} base={`/api/order/${threadId}`}
            editable onClose={() => setInvViewer(null)} />
        )}
      </section>
      </div>{/* #od-invoice */}
      <div id="od-stock">
      <OrderStock threadId={threadId} invoice={j.invoice || []} stockConfirmed={j.stock_confirmed || null} />
      </div>
      <div id="od-payments">
      <Payments threadId={threadId} payments={j.payments || []} suggest={invoiceTotal(j.invoice)} onChanged={changed} />
      </div>
      <Images base={`/api/order/${threadId}`} anchorId="od-camera" openSignal={camSignal} />
      <History base={`/api/order/${threadId}`} />
      <div class="muted small center">Tạo bởi: {(j.nguoi_tao_HD || []).join(", ") || "?"} · thread {threadId}</div>

      {isAdmin && (
        <section class="card" style={{ marginTop: "10px" }}>
          <button class={"btn danger block" + (delOrderLock ? " faded" : "")} onClick={doDeleteOrder}
            title={delOrderLock || undefined}>
            <Icon name="trash" size={16} /> Xoá đơn (admin)
          </button>
          <div class="muted small">
            {delOrderLock ? delOrderLock : "Chỉ xoá được khi không có HĐ KiotViet, không thanh toán, không còn phân bổ kho."}
          </div>
        </section>
      )}
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
