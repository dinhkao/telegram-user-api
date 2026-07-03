// Chi tiết đơn — header + text + ghép các khối detail/* (tasks, invoice,
// payments, comments). Data: GET /api/order/{thread_id}. In: POST /api/order/print-giao.
import { useEffect, useRef, useState } from "preact/hooks";
import { createKiotVietInvoice, currentUser, deleteKiotVietInvoice, getJSON, invoiceHtmlUrl, postJSON, refreshOrderDebt } from "../api";
import { onRealtime } from "../realtime";
import { money, invoiceTotal, paidTotal } from "../format";
import { Comments } from "../detail/Comments";
import { InvoiceEditor, type EditorPayload } from "../detail/InvoiceEditor";
import { CustomerPicker } from "../detail/CustomerPicker";
import { Payments } from "../detail/Payments";
import { Tasks } from "../detail/Tasks";
import { History } from "../detail/History";
import { Images } from "../detail/Images";
import { invalidateListCache, markLastOrder } from "./OrdersList";

// Nhớ vị trí cuộn theo từng đơn — quay lại đơn cũ về đúng chỗ đang xem
const detailScroll: Record<string, number> = {};

export function OrderDetail({ threadId, focus }: { threadId: string; focus?: string }) {
  const [detail, setDetail] = useState<any>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [editText, setEditText] = useState<string | null>(null);
  const [changingCust, setChangingCust] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const seenTs = useRef<string | null>(null); // ts mới nhất đã báo — chặn báo lại lịch sử cũ
  const restored = useRef(false); // đã khôi phục vị trí cuộn cho đơn này chưa
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
  useEffect(() => {
    restored.current = !!focus; // có focus (từ notification) → bỏ khôi phục cuộn, để focus thắng
    markLastOrder(threadId); // ghi nhận đơn vừa mở → dashboard tô sáng khi quay lại
    reload();
  }, [threadId]);

  // Lưu vị trí cuộn khi rời đơn (đổi đơn / thoát trang) để lần sau về đúng chỗ
  useEffect(() => {
    return () => { detailScroll[threadId] = window.scrollY; };
  }, [threadId]);

  // Khôi phục vị trí cuộn: các khối con (bình luận/ảnh/lịch sử) tải BẤT ĐỒNG BỘ nên
  // trang cao dần — áp lại scrollTo nhiều lần cho tới khi trang đủ cao/đạt đích; huỷ
  // ngay khi người dùng tự cuộn (không giằng co). Chạy 1 lần mỗi lần mở đơn.
  useEffect(() => {
    if (focus || restored.current) return;
    restored.current = true;
    const y = detailScroll[threadId] || 0;
    if (y <= 4) return;
    let cancelled = false;
    const onUser = () => { cancelled = true; done(); };
    const done = () => {
      clearInterval(iv); clearTimeout(to);
      window.removeEventListener("wheel", onUser);
      window.removeEventListener("touchstart", onUser);
      window.removeEventListener("keydown", onUser);
    };
    const tryScroll = () => {
      if (cancelled) return;
      window.scrollTo(0, y);
      if (Math.abs(window.scrollY - y) <= 2) done(); // đạt đích (trang đã đủ cao)
    };
    window.addEventListener("wheel", onUser, { passive: true });
    window.addEventListener("touchstart", onUser, { passive: true });
    window.addEventListener("keydown", onUser);
    const iv = setInterval(tryScroll, 80);
    const to = setTimeout(done, 2500);
    tryScroll();
    return done;
  }, [threadId, focus]);

  // Deep-link notification: đợi phần tử (bình luận/ảnh) render rồi cuộn tới + nháy sáng
  useEffect(() => {
    if (!focus) return;
    let tries = 0;
    let flashT: any;
    const iv = setInterval(() => {
      const el = document.getElementById(focus);
      if (el) {
        clearInterval(iv);
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.classList.add("flash-target");
        flashT = setTimeout(() => el.classList.remove("flash-target"), 2400);
        history.replaceState(null, "", `#/order/${threadId}`); // xoá ?focus khỏi URL
      } else if (++tries > 50) {
        clearInterval(iv); // ~5s không thấy → thôi
      }
    }, 100);
    return () => { clearInterval(iv); clearTimeout(flashT); };
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
    let t: any, tt: any, hide: any;
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
            setToast(msg);
            clearTimeout(hide); hide = setTimeout(() => setToast(null), Math.min(10000, 4000 + fresh.length * 1200));
          } catch { /* ignore */ }
        }, 600);
      }
    });
    return () => { off(); clearTimeout(t); clearTimeout(tt); clearTimeout(hide); };
  }, [threadId]);

  if (err && !detail) return <p class="error">{err}</p>;
  if (!detail) return <p class="muted center">Đang tải…</p>;

  const j = detail.data || {};
  const pc = (j.hoadon || {}).print_content || {};
  const isAdmin = currentUser()?.role === "admin";
  // ưu tiên tổng từ hoá đơn in (đã gồm mọi điều chỉnh); tự tính thì phải cộng trừ
  // discount/pvc/vat như /api/order/totals — không thì lệch với Telegram
  const computedTotal = invoiceTotal(j.invoice) - (Number(j.discount) || 0) + (Number(j.pvc) || 0) + (Number(j.vat) || 0);
  const total = pc.tongthanhtoan ? pc.tongthanhtoan : money(computedTotal);
  const paid = paidTotal(j.payments);

  const doPrint = async () => {
    if (!confirm("In 2 hoá đơn + phiếu giao?")) return;
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
    if (!confirm("Tạo hoá đơn KiotViet cho đơn này?")) return;
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
    if (!confirm("XOÁ hoá đơn KiotViet của đơn này? Không thể hoàn tác.")) return;
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
      {toast && <div class="toast" onClick={() => setToast(null)}>{toast}</div>}
      <header class="detail-head">
        <a href="#/orders" class="back">←</a>
        <div>
          <b>{pc.kh || j.customer_name || j.topic_name || `#${threadId}`}</b>
          <div class="muted small">
            {j.kiotvietInvoiceCode || (j.hoadon || {}).hd_code || ""} {pc.datetime ? `· ${pc.datetime}` : ""}
          </div>
        </div>
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
          <pre class="order-text">{j.text || j.text_raw || "(trống)"}</pre>
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
      <div class="card">
        <div class="row space"><span>Đã trả</span><b>{money(paid)}đ</b></div>
        {pc.no_truoc && <div class="row space"><span>Nợ trước</span><b>{pc.no_truoc}đ</b></div>}
        {(j.khach_hang_id || j.khID) && (
          <div class="row space">
            <span>Nợ khách (KiotViet)</span>
            <span class="row">
              {(j.khDebt != null || j.invoice_debt_snapshot != null)
                ? <b>{money(j.khDebt ?? j.invoice_debt_snapshot)}đ</b>
                : <span class="muted small">chưa có</span>}
              <button class="btn small" title="Kéo nợ KiotViet mới nhất" onClick={refreshDebt}>🔄</button>
            </span>
          </div>
        )}
      </div>

      <div class="card">
        <div class="row space">
          <span>Khách hàng</span>
          {(j.customer_name || j.khach_hang_id) && !changingCust && (
            <button class="btn small" onClick={() => setChangingCust(true)}>Đổi</button>
          )}
        </div>
        {(j.customer_name || j.khach_hang_id) && !changingCust ? (
          <b>{j.customer_name || pc.kh}</b>
        ) : (
          <div>
            {!(j.customer_name || j.khach_hang_id) && <p class="muted small">⚠️ Đơn chưa có khách — tìm và gán để lấy giá + tạo HĐ.</p>}
            <CustomerPicker onPick={assignCustomer} placeholder="🔍 Tìm khách để gán" />
            {changingCust && <button class="btn small" onClick={() => setChangingCust(false)}>Huỷ</button>}
          </div>
        )}
      </div>

      <Tasks threadId={threadId} taskStatus={j.task_status || {}} userNames={detail.user_names || {}} onChanged={changed} />
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
        onView={() => window.open(invoiceHtmlUrl(threadId), "_blank")}
        onDelete={deleteHD}
        onPrint={doPrint}
        canDelete={isAdmin}
        invoiceCode={j.kiotvietInvoiceCode || j.kiotvietInvoiceID}
      />
      <Payments threadId={threadId} payments={j.payments || []} onChanged={changed} />
      <Images threadId={threadId} />
      <History threadId={threadId} />
      <div class="muted small center">Tạo bởi: {(j.nguoi_tao_HD || []).join(", ") || "?"} · thread {threadId}</div>
      </div>{/* .dmain */}

      <aside class="dside">
        <Comments threadId={threadId} chatMessages={detail.chat_messages || []} />
      </aside>
      </div>{/* .detail-grid */}
    </div>
  );
}
