// Chi tiết đơn — header + text + ghép các khối detail/* (tasks, invoice,
// payments, comments). Data: GET /api/order/{thread_id}. In: POST /api/order/print-giao.
import { useEffect, useState } from "preact/hooks";
import { getJSON, postJSON } from "../api";
import { money, invoiceTotal, paidTotal } from "../format";
import { Comments } from "../detail/Comments";
import { InvoiceBlock } from "../detail/Invoice";
import { Payments } from "../detail/Payments";
import { Tasks } from "../detail/Tasks";

export function OrderDetail({ threadId }: { threadId: string }) {
  const [detail, setDetail] = useState<any>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [editText, setEditText] = useState<string | null>(null);

  const reload = async () => {
    try {
      setDetail(await getJSON(`/api/order/${threadId}`));
      setErr("");
    } catch (ex: any) {
      setErr(ex.message);
    }
  };
  useEffect(() => {
    reload();
  }, [threadId]);

  if (err && !detail) return <p class="error">{err}</p>;
  if (!detail) return <p class="muted center">Đang tải…</p>;

  const j = detail.data || {};
  const pc = (j.hoadon || {}).print_content || {};
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

  const saveText = async () => {
    if (editText === null) return;
    setBusy(true);
    try {
      await postJSON("/api/order/fix", { thread_id: Number(threadId), text: editText });
      setMsg("✅ Đã sửa text — hệ thống đang parse lại");
      setEditText(null);
      setTimeout(reload, 1500);
    } catch (ex: any) {
      setMsg(`❌ ${ex.message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div class="detail">
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

      <div class="card">
        <div class="row space"><span>Tổng tiền</span><b class="money">{total}đ</b></div>
        <div class="row space"><span>Đã trả</span><b>{money(paid)}đ</b></div>
        {pc.no_truoc && <div class="row space"><span>Nợ trước</span><b>{pc.no_truoc}đ</b></div>}
      </div>

      <Tasks threadId={threadId} taskStatus={j.task_status || {}} onChanged={reload} />
      <InvoiceBlock threadId={threadId} invoice={j.invoice || []} onChanged={reload} />
      <Payments threadId={threadId} payments={j.payments || []} onChanged={reload} />

      <div class="card">
        <div class="row space">
          <b>Text đơn</b>
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

      <Comments threadId={threadId} chatMessages={detail.chat_messages || []} />

      <button class="btn wide" disabled={busy} onClick={doPrint}>🖨️ In hoá đơn + phiếu giao</button>
      <div class="muted small center">Tạo bởi: {(j.nguoi_tao_HD || []).join(", ") || "?"} · thread {threadId}</div>
    </div>
  );
}
