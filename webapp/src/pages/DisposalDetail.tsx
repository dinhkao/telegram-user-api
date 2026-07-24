// Chi tiết phiếu XUẤT HỦY (#/xuat-huy/:id) — lý do + các thùng đã hủy (link về
// thùng). Ảnh chứng minh hàng hư + trao đổi + lịch sử = entity media scope
// 'disposal'. Xoá = admin: TỒN HOÀN LẠI các thùng, phiếu xoá mềm.
import { useEffect, useState } from "preact/hooks";
import { PageHead } from "../ui/PageHead";
import { currentUser, deleteDisposal, getDisposal, soVN, type DisposalSlip } from "../api";
import { fmtDateTimeVN } from "../format";
import { onRealtime } from "../realtime";
import { Images } from "../detail/Images";
import { Comments } from "../detail/Comments";
import { History } from "../detail/History";
import { confirmDialog, toast } from "../ui/feedback";
import { ErrorState, Loading } from "../ui/states";
import { Icon } from "../ui/Icon";

export function DisposalDetail({ id }: { id: string }) {
  const [r, setR] = useState<DisposalSlip | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const isAdmin = currentUser()?.role === "admin";

  const load = () => getDisposal(id).then(setR).catch((e: any) => setErr(e?.message || "Lỗi tải phiếu"));
  useEffect(() => { load(); }, [id]);
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      const hit = e.type === "resync" || (e.type === "disposal_changed" && e.id === String(id));
      if (hit) { clearTimeout(t); t = setTimeout(load, 250); }
    });
    return () => { off(); clearTimeout(t); };
  }, [id]);

  if (err) return <ErrorState msg={err} onRetry={load} />;
  if (!r) return <Loading />;
  const deleted = !!r.deleted_at;

  const doDelete = async () => {
    if (!isAdmin) return toast("Chỉ admin mới được xoá phiếu hủy", "info");
    if (!(await confirmDialog(
      r.box_less
        ? "Xoá phiếu hủy hàng trả này? (Chỉ gỡ bản ghi — không có tồn kho để hoàn.)"
        : `Xoá phiếu hủy này? Tồn kho sẽ HOÀN LẠI ${soVN(r.total_quantity)} vào các thùng.`,
      { danger: true, okLabel: r.box_less ? "Xoá phiếu" : "Xoá + hoàn tồn" }))) return;
    setBusy(true);
    try {
      await deleteDisposal(Number(id));
      toast("Đã xoá phiếu — tồn kho hoàn lại", "ok");
      window.location.hash = "#/xuat-huy";
    } catch (e: any) {
      toast(e?.message || "Lỗi xoá phiếu", "err");
    } finally { setBusy(false); }
  };

  return (
    <div class="ret-detail">
      <PageHead fallback="#/xuat-huy"
        title={<><Icon name="trash" size={18} /> Xuất hủy −{soVN(r.total_quantity)}</>}
        sub={<>{fmtDateTimeVN(r.created_at)}{r.created_by ? ` · ${r.created_by}` : ""}</>} />
      {deleted && <div class="error-banner">Phiếu đã bị xoá{r.deleted_by ? ` bởi ${r.deleted_by}` : ""}{r.box_less ? "" : " — tồn kho đã hoàn lại"}</div>}
      {r.box_less && (
        <div class="disp-boxless-note">
          <Icon name="refresh" size={14} /> Hàng khách trả — chỉ GHI NHẬN hủy, không trừ tồn kho.
          {r.source_return_id ? <> Từ <a href={`#/tra-hang/${r.source_return_id}`}>phiếu trả #{r.source_return_id}</a>.</> : null}
        </div>
      )}

      <section class="card">
        <label class="card-label"><Icon name="note" size={15} /> Lý do hủy</label>
        <div class="disp-reason">{r.reason}</div>
      </section>

      <section class="card">
        <label class="card-label"><Icon name="box" size={15} /> Hàng đã hủy</label>
        <table class="ret-items">
          <thead><tr><th>SP</th><th>{r.box_less ? "Đơn vị" : "Thùng"}</th><th>SL hủy</th></tr></thead>
          <tbody>
            {(r.items || []).map((x, i) => (
              <tr key={i}>
                <td><b>{x.product_code}</b></td>
                <td>{x.box_id
                  ? <a href={`#/thung/${x.box_id}`}>{(x.box_code || "").split("-").pop() || x.box_code}</a>
                  : <span class="muted">{x.product_unit || "—"}</span>}</td>
                <td>−{soVN(x.quantity)}</td>
              </tr>
            ))}
            <tr class="ret-sum"><td colSpan={2}>Tổng hủy</td><td><b>−{soVN(r.total_quantity)}</b></td></tr>
          </tbody>
        </table>
      </section>

      <Images base={`/api/media/disposal/${id}`} />
      <Comments base={`/api/media/disposal/${id}`} />
      <History base={`/api/media/disposal/${id}`} />

      {!deleted && (
        <button class={"btn danger block" + (isAdmin ? "" : " faded")} disabled={busy} onClick={doDelete}>
          <Icon name="trash" size={15} /> {busy ? "Đang xoá…" : "Xoá phiếu (hoàn tồn kho)"}
        </button>
      )}
    </div>
  );
}
