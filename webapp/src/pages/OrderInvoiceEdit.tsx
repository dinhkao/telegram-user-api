// Trang "Sửa hoá đơn" của 1 đơn (#/order/:id/hoa-don) — THUẦN chỉnh sửa sản
// phẩm/CK/PVC/VAT: lưu xong quay về chi tiết đơn. Mọi thao tác HĐ KiotViet
// (tạo/xem/in/xoá/kéo nợ) nằm ở khối Hoá đơn của OrderDetail. Đơn đã có HĐ
// KiotViet → khoá, không sửa được (phải xoá HĐ trước).
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { getJSON, postJSON } from "../api";
import { InvoiceEditor, type EditorPayload } from "../detail/InvoiceEditor";
import { invalidateListCache } from "./OrdersList";
import { toast } from "../ui/feedback";
import { Loading, ErrorState } from "../ui/states";
import { Icon } from "../ui/Icon";

export function OrderInvoiceEdit({ threadId }: { threadId: string }) {
  const [detail, setDetail] = useState<any>(null);
  const [err, setErr] = useState("");

  const reload = async () => {
    try { setDetail(await getJSON(`/api/order/${threadId}`)); setErr(""); }
    catch (ex: any) { setErr(ex.message); }
  };
  useEffect(() => { reload(); }, [threadId]);

  const goBack = () => { window.location.hash = `#/order/${threadId}`; };
  const saveInvoice = async (payload: EditorPayload) => {
    await postJSON("/api/order/invoice/update", { thread_id: Number(threadId), ...payload });
    invalidateListCache();
    toast("✅ Đã lưu hoá đơn", "ok");
    goBack();
  };

  if (err) return <ErrorState msg={err} onRetry={reload} />;
  if (!detail) return <Loading />;
  const j = detail.data || {};
  const locked = !!j.kiotvietInvoiceID;

  return (
    <div>
      <div class="prod-detail-head">
        <BackLink fallback={`#/order/${threadId}`} />
        <div><div class="prod-sp big">Sửa hoá đơn · đơn #{threadId}</div></div>
      </div>
      {locked ? (
        <div class="card co-adv-locked muted small">
          <Icon name="lock" size={14} /> Đơn đã tạo hoá đơn KiotViet ({j.kiotvietInvoiceCode || j.kiotvietInvoiceID}) —
          không sửa được. Muốn sửa phải xoá HĐ ở trang chi tiết trước.
        </div>
      ) : (
        <InvoiceEditor
          customerId={j.khach_hang_id || j.khID}
          invoice={j.invoice || []}
          discount={j.discount}
          pvc={j.pvc}
          vat={j.vat}
          onSave={saveInvoice}
          onCancel={goBack}
        />
      )}
    </div>
  );
}
