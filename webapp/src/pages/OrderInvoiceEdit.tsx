// Trang "Sửa hoá đơn" của 1 đơn (#/order/:id/hoa-don) — THUẦN chỉnh sửa sản
// phẩm/CK/PVC/VAT: lưu xong quay về chi tiết đơn. Mọi thao tác HĐ KiotViet
// (tạo/xem/in/xoá/kéo nợ) nằm ở khối Hoá đơn của OrderDetail. Đơn đã có HĐ
// KiotViet → khoá, không sửa được (phải xoá HĐ trước).
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { getJSON, postJSON, lockInvoiceEdit, unlockInvoiceEdit } from "../api";
import { InvoiceEditor, type EditorPayload } from "../detail/InvoiceEditor";
import { invalidateListCache } from "./OrdersList";
import { toast } from "../ui/feedback";
import { Loading, ErrorState } from "../ui/states";
import { Icon } from "../ui/Icon";

export function OrderInvoiceEdit({ threadId }: { threadId: string }) {
  const [detail, setDetail] = useState<any>(null);
  const [err, setErr] = useState("");
  const [editHolder, setEditHolder] = useState<string | null>(null);   // NGƯỜI KHÁC đang sửa

  const reload = async () => {
    try { setDetail(await getJSON(`/api/order/${threadId}`)); setErr(""); }
    catch (ex: any) { setErr(ex.message); }
  };
  useEffect(() => { reload(); }, [threadId]);

  const j = detail?.data || {};
  const hasInvoice = !!j.kiotvietInvoiceID;
  const stockLocked = !!j.stock_confirmed;   // đã chốt xuất kho → khoá dù đã xoá HĐ
  const locked = hasInvoice || stockLocked;
  const editable = !!detail && !locked;      // chỉ giữ khoá khi đơn còn sửa được

  // Giữ khoá "1 người sửa hoá đơn" khi trang mở: heartbeat 20s, nhả khi rời trang. Người khác
  // giữ (mine=false) → hiện banner + poll nhanh 4s để bắt lúc họ nhả rồi tự vào sửa.
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

  const goBack = () => { window.location.hash = `#/order/${threadId}`; };
  const saveInvoice = async (payload: EditorPayload) => {
    await postJSON("/api/order/invoice/update", { thread_id: Number(threadId), ...payload });
    invalidateListCache();
    toast("✅ Đã lưu hoá đơn", "ok");
    goBack();
  };

  if (err) return <ErrorState msg={err} onRetry={reload} />;
  if (!detail) return <Loading />;

  return (
    <div>
      <div class="prod-detail-head">
        <BackLink fallback={`#/order/${threadId}`} />
        <div><div class="prod-sp big">Sửa hoá đơn · đơn #{threadId}</div></div>
      </div>
      {locked ? (
        <div class="card co-adv-locked muted small">
          <Icon name="lock" size={14} />{" "}
          {hasInvoice
            ? <>Đơn đã tạo hoá đơn KiotViet ({j.kiotvietInvoiceCode || j.kiotvietInvoiceID}) — không sửa được. Muốn sửa phải xoá HĐ ở trang chi tiết trước.</>
            : <>Đơn đã <b>chốt xuất kho</b> — không sửa hoá đơn được. Admin bấm <b>Huỷ chốt</b> ở khối Xuất kho mới sửa được.</>}
        </div>
      ) : editHolder ? (
        <div class="card co-adv-locked muted small">
          <Icon name="lock" size={14} /> <b>{editHolder}</b> đang sửa hoá đơn đơn này — chờ họ xong.
          Trang sẽ tự mở cho bạn khi họ rời.
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
