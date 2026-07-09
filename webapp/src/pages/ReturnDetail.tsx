// Chi tiết phiếu TRẢ HÀNG (#/tra-hang/:id) — bảng hàng trả, khách (link), HĐ KV,
// nợ trước/sau, người tạo. Xoá = admin (fade + toast khi không đủ quyền; server chặn).
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { getReturn, deleteReturn, currentUser, soVN, type ReturnSlip } from "../api";
import { onRealtime } from "../realtime";
import { confirmDialog, toast } from "../ui/feedback";
import { Loading, ErrorState } from "../ui/states";
import { Icon } from "../ui/Icon";

export function ReturnDetail({ id }: { id: string }) {
  const [r, setR] = useState<ReturnSlip | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const isAdmin = currentUser()?.role === "admin";

  const load = () => getReturn(id).then(setR).catch((e: any) => setErr(e?.message || "Lỗi tải phiếu"));
  useEffect(() => { load(); }, [id]);
  useEffect(() => onRealtime((e) => {
    if (e.type === "customer_changed" || e.type === "resync") load();
  }), [id]);

  const doDelete = async () => {
    if (!isAdmin) return toast("Chỉ admin mới được xoá phiếu trả", "info");
    if (!(await confirmDialog("Xoá phiếu trả này? HĐ KiotViet giá âm sẽ bị xoá và công nợ khách CỘNG lại.", { danger: true }))) return;
    setBusy(true);
    try {
      await deleteReturn(Number(id));
      toast("Đã xoá phiếu trả", "ok");
      window.location.hash = "#/tra-hang";
    } catch (e: any) {
      toast(e?.message || "Lỗi xoá phiếu", "err");
    } finally {
      setBusy(false);
    }
  };

  if (err) return <ErrorState msg={err} onRetry={load} />;
  if (!r) return <Loading />;
  const deleted = !!(r as any).deleted_at;

  return (
    <div class="ret-detail">
      <div class="prod-detail-head">
        <BackLink fallback="#/tra-hang" />
        <div>
          <div class="prod-sp big"><Icon name="refresh" size={18} /> Trả hàng −{soVN(r.total)}đ</div>
          <div class="prod-date muted">{r.created_at ? `${r.created_at.slice(8, 10)}/${r.created_at.slice(5, 7)}/${r.created_at.slice(0, 4)} ${r.created_at.slice(11, 16)}` : ""}{r.created_by ? ` · ${r.created_by}` : ""}</div>
        </div>
      </div>
      {deleted && <div class="error-banner">Phiếu đã bị xoá{(r as any).deleted_by ? ` bởi ${(r as any).deleted_by}` : ""}</div>}

      <section class="card">
        <label class="card-label"><Icon name="user" size={15} /> Khách hàng</label>
        <a class="ret-cust-link" href={`#/khach/${encodeURIComponent(r.customer_key)}`}>
          {r.customer_name || r.customer_key} <Icon name="link" size={13} />
        </a>
        <div class="muted small">
          Nợ trước: <b>{r.debt_before != null ? soVN(r.debt_before) : "—"}</b>
          {" → "}sau: <b>{r.debt_after != null ? soVN(r.debt_after) : "—"}</b>
        </div>
      </section>

      <section class="card">
        <label class="card-label"><Icon name="box" size={15} /> Hàng trả</label>
        <table class="ret-items">
          <thead><tr><th>SP</th><th>SL</th><th>Giá</th><th>Tổng</th></tr></thead>
          <tbody>
            {(r.items || []).map((x, i) => (
              <tr key={i}>
                <td><b>{x.sp}</b></td>
                <td>{soVN(x.sl)}</td>
                <td>{soVN(x.price)}</td>
                <td>{soVN(x.sl * x.price)}</td>
              </tr>
            ))}
            <tr class="ret-sum"><td colSpan={3}>Tổng trả (trừ nợ)</td><td><b>−{soVN(r.total)}</b></td></tr>
          </tbody>
        </table>
        {r.note && <div class="ret-card-note"><Icon name="note" size={13} /> {r.note}</div>}
      </section>

      <section class="card">
        <label class="card-label"><Icon name="receipt" size={15} /> Hoá đơn KiotViet (giá âm)</label>
        <div>{r.kv_invoice_code || "—"} {r.kv_invoice_id ? <span class="muted small">· #{r.kv_invoice_id}</span> : null}</div>
      </section>

      {!deleted && (
        <button class={"btn danger block" + (isAdmin ? "" : " faded")} disabled={busy} onClick={doDelete}>
          <Icon name="trash" size={15} /> {busy ? "Đang xoá…" : "Xoá phiếu trả (hoàn nợ)"}
        </button>
      )}
    </div>
  );
}
