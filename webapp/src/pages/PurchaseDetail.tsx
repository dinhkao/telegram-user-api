// Chi tiết phiếu NHẬP HÀNG (#/nhap-hang/:id) — giống trang đơn/phiếu trả nhưng
// 100% local (không KiotViet): văn phòng sửa hàng nhập/ghi chú ở trang riêng; ảnh +
// trao đổi + lịch sử dùng entity media scope 'purchase'. Xoá = admin (xoá mềm).
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import {
  getPurchase, deletePurchase, currentUser, isOffice, soVN, type PurchaseSlip,
} from "../api";
import { onRealtime } from "../realtime";
import { Images } from "../detail/Images";
import { Comments } from "../detail/Comments";
import { History } from "../detail/History";
import { confirmDialog, toast } from "../ui/feedback";
import { Loading, ErrorState } from "../ui/states";
import { Icon } from "../ui/Icon";

export function PurchaseDetail({ id }: { id: string }) {
  const [r, setR] = useState<PurchaseSlip | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const isAdmin = currentUser()?.role === "admin";
  const office = isOffice();

  const load = () => getPurchase(id).then(setR).catch((e: any) => setErr(e?.message || "Lỗi tải phiếu"));
  useEffect(() => { load(); }, [id]);
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      const hit = e.type === "resync" || (e.type === "purchase_changed" && e.id === String(id));
      if (hit) { clearTimeout(t); t = setTimeout(load, 250); }
    });
    return () => { off(); clearTimeout(t); };
  }, [id]);

  if (err) return <ErrorState msg={err} onRetry={load} />;
  if (!r) return <Loading />;
  const deleted = !!r.deleted_at;

  const doDelete = async () => {
    if (!isAdmin) return toast("Chỉ admin mới được xoá phiếu nhập", "info");
    if (!(await confirmDialog("Xoá phiếu nhập này?", { danger: true }))) return;
    setBusy(true);
    try {
      await deletePurchase(Number(id));
      toast("Đã xoá phiếu nhập", "ok");
      window.location.hash = "#/nhap-hang";
    } catch (e: any) {
      toast(e?.message || "Lỗi xoá phiếu", "err");
    } finally { setBusy(false); }
  };

  return (
    <div class="ret-detail">
      <div class="prod-detail-head">
        <BackLink fallback="#/nhap-hang" />
        <div>
          <div class="prod-sp big">
            <Icon name="truck" size={18} /> Nhập hàng {soVN(r.total)}đ
          </div>
          <div class="prod-date muted">{r.created_at ? `${r.created_at.slice(8, 10)}/${r.created_at.slice(5, 7)}/${r.created_at.slice(0, 4)} ${r.created_at.slice(11, 16)}` : ""}{r.created_by ? ` · ${r.created_by}` : ""}</div>
        </div>
        {!deleted && (
          <a
            class={"btn small ret-edit" + (office ? "" : " faded")}
            href={`#/nhap-hang/${id}/sua`}
            onClick={(e) => {
              if (!office) {
                e.preventDefault();
                toast("Chỉ văn phòng mới được sửa phiếu nhập", "info");
              }
            }}
          >
            <Icon name="edit" size={13} /> Sửa
          </a>
        )}
      </div>
      {deleted && <div class="error-banner">Phiếu đã bị xoá{r.deleted_by ? ` bởi ${r.deleted_by}` : ""}</div>}

      <section class="card">
        <label class="card-label"><Icon name="users" size={15} /> Nhà cung cấp</label>
        <a class="ret-cust-link" href={`#/ncc/${r.supplier_id}`}>
          {r.supplier_name || `NCC #${r.supplier_id}`} <Icon name="link" size={13} />
        </a>
      </section>

      <section class="card">
        <label class="card-label"><Icon name="box" size={15} /> Hàng nhập
        </label>
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
            <tr class="ret-sum"><td colSpan={3}>Tổng nhập</td><td><b>{soVN(r.total)}</b></td></tr>
          </tbody>
        </table>
        {r.note && <div class="ret-card-note"><Icon name="note" size={13} /> {r.note}</div>}
      </section>

      <Images base={`/api/media/purchase/${id}`} />
      <Comments base={`/api/media/purchase/${id}`} />
      <History base={`/api/media/purchase/${id}`} />

      {!deleted && (
        <button class={"btn danger block" + (isAdmin ? "" : " faded")} disabled={busy} onClick={doDelete}>
          <Icon name="trash" size={15} /> {busy ? "Đang xoá…" : "Xoá phiếu nhập"}
        </button>
      )}
    </div>
  );
}
