// Trang riêng "Sửa hoá đơn" của 1 đơn (#/order/:id/hoa-don) — tách khỏi OrderDetail.
// Tải đơn, render InvoiceEditor + mọi thao tác HĐ (lưu/tạo/xoá/in/xem/kéo nợ KiotViet).
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import {
  createKiotVietInvoice, currentUser, deleteKiotVietInvoice, getJSON, invoiceHtmlUrl,
  listOrderImages, orderImageUrl, postJSON, refreshOrderDebt,
} from "../api";
import { money } from "../format";
import { InvoiceEditor, type EditorPayload } from "../detail/InvoiceEditor";
import { invalidateListCache } from "./OrdersList";
import { confirmDialog } from "../ui/feedback";
import { Loading, ErrorState } from "../ui/states";

export function OrderInvoiceEdit({ threadId }: { threadId: string }) {
  const [detail, setDetail] = useState<any>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const isAdmin = currentUser()?.role === "admin";

  const reload = async () => {
    try { setDetail(await getJSON(`/api/order/${threadId}`)); setErr(""); }
    catch (ex: any) { setErr(ex.message); }
  };
  const changed = () => { invalidateListCache(); reload(); };
  useEffect(() => { reload(); }, [threadId]);

  const findInvoiceImageUrl = async (): Promise<string | null> => {
    try {
      const imgs = await listOrderImages(threadId);
      const inv = imgs.find((x) => x.kind === "hoa_don" || x.uploaded_by === "KiotViet HĐ");
      return inv ? orderImageUrl(threadId, inv.id, "full") : null;
    } catch { return null; }
  };
  const saveInvoice = async (payload: EditorPayload) => {
    await postJSON("/api/order/invoice/update", { thread_id: Number(threadId), ...payload });
    setMsg("✅ Đã lưu hoá đơn"); changed();
  };
  const createHD = async () => {
    if (!(await confirmDialog("Tạo hoá đơn KiotViet cho đơn này?"))) return;
    try {
      const r = await createKiotVietInvoice(threadId);
      setMsg(`🧾 Đã tạo HĐ ${r.kv_code || ""}${r.old_debt ? ` · nợ cũ ${money(r.old_debt)}đ` : ""}`); changed();
    } catch (ex: any) { setMsg(`❌ ${ex.message}`); }
  };
  const deleteHD = async () => {
    if (!(await confirmDialog("XOÁ hoá đơn KiotViet của đơn này? Không thể hoàn tác.", { danger: true }))) return;
    try { await deleteKiotVietInvoice(threadId); setMsg("🗑️ Đã xoá hoá đơn KiotViet"); changed(); }
    catch (ex: any) { setMsg(`❌ ${ex.message}`); }
  };
  const doPrint = async () => {
    const imgUrl = await findInvoiceImageUrl();
    if (!(await confirmDialog("In 2 hoá đơn + phiếu giao?", { okLabel: "In", imageUrl: imgUrl || undefined }))) return;
    setBusy(true);
    try {
      const r = await postJSON("/api/order/print-giao", { thread_id: Number(threadId) });
      setMsg(r.error ? `❌ ${r.error}` : "🖨️ Đã gửi lệnh in");
    } catch (ex: any) { setMsg(`❌ ${ex.message}`); } finally { setBusy(false); }
  };
  const refreshDebt = async () => {
    try { const r = await refreshOrderDebt(threadId); setMsg(`💰 Đã cập nhật nợ KiotViet: ${money(r.debt)}đ`); changed(); }
    catch (ex: any) { setMsg(`❌ ${ex.message}`); }
  };

  if (err) return <ErrorState msg={err} onRetry={reload} />;
  if (!detail) return <Loading />;
  const j = detail.data || {};

  return (
    <div>
      <div class="prod-detail-head">
        <BackLink fallback={`#/order/${threadId}`} />
        <div><div class="prod-sp big">Hoá đơn · đơn #{threadId}</div></div>
      </div>
      {msg && <div class="muted small" style={{ margin: "4px 0 8px" }}>{msg}</div>}
      <InvoiceEditor
        customerId={j.khach_hang_id || j.khID}
        invoice={j.invoice || []}
        discount={j.discount}
        pvc={j.pvc}
        vat={j.vat}
        onSave={saveInvoice}
        onCreateInvoice={createHD}
        startEditing={!j.kiotvietInvoiceID}
        canCreate={isAdmin}
        hasInvoice={!!j.kiotvietInvoiceID}
        debt={j.khDebt ?? j.invoice_debt_snapshot}
        onView={async () => {
          const win = window.open("", "_blank");
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
    </div>
  );
}
