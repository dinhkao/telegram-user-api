// Chi tiết 1 PHIẾU KHO ĐẬU (#/kho-dau/phieu/:id) — loại phiếu, kho, ngày, người
// tạo + từng dòng đậu (số ghi trên phiếu, tồn trước, biến động). Xoá = admin
// (tồn tự hoàn lại). Realtime: bean_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import {
  BEAN_KIND_LABEL, currentUser, deleteBeanSlip, getBeanSlip, soVN, type BeanSlip,
} from "../api";
import { fmtDateTimeVN } from "../format";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { confirmDialog, toast } from "../ui/feedback";
import { ErrorState, Loading } from "../ui/states";

export function BeanSlipDetail({ id }: { id: string }) {
  const [slip, setSlip] = useState<BeanSlip | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const isAdmin = currentUser()?.role === "admin";

  const load = () => getBeanSlip(id)
    .then((s) => { setSlip(s); setErr(""); })
    .catch((e: any) => setErr(e?.message || "Lỗi tải phiếu"));
  useEffect(() => { load(); }, [id]);
  useEffect(() => onRealtime((e) => {
    if (e.type === "bean_changed" || e.type === "resync") load();
  }), [id]);

  const del = async () => {
    if (!slip) return;
    if (!(await confirmDialog(
      `Xoá phiếu ${BEAN_KIND_LABEL[slip.kind].toLowerCase()} #${slip.id}? Tồn kho sẽ hoàn lại như trước.`,
      { danger: true, okLabel: "Xoá phiếu" }))) return;
    setBusy(true);
    try {
      await deleteBeanSlip(slip.id);
      toast("Đã xoá phiếu", "ok");
      window.location.hash = "#/kho-dau/phieu";
    } catch (e: any) {
      toast(e?.message || "Lỗi xoá phiếu", "err");
    } finally {
      setBusy(false);
    }
  };

  if (err) return <ErrorState msg={err} onRetry={() => { setErr(""); load(); }} />;
  if (!slip) return <Loading />;

  const isAdj = slip.kind === "dieu_chinh";
  return (
    <div class="bean-detail">
      <PageHead fallback="#/kho-dau/phieu"
        title={<>{BEAN_KIND_LABEL[slip.kind]} <span class="muted small">#{slip.id}</span></>}
        sub={`${slip.place_name} · ngày ${slip.ymd}`}
        right={isAdmin ? (
          <button class="btn small danger" disabled={busy} onClick={del}>
            <Icon name="trash" size={15} />
          </button>
        ) : undefined} />

      <div class="bean-meta muted small">
        Người tạo: {slip.created_by || "—"} · {fmtDateTimeVN(slip.created_at)}
        {slip.partner ? <> · {slip.kind === "nhap" ? "nhập từ" : slip.kind === "xuat" ? "xuất cho" : "người kiểm"}: <b>{slip.partner}</b></> : null}
      </div>
      {slip.note ? <div class="bean-note">“{slip.note}”</div> : null}

      <table class="bean-table">
        <thead>
          <tr>
            <th>Loại đậu</th>
            <th class="num">{isAdj ? "Đếm thực tế" : "Số lượng"}</th>
            {isAdj && <th class="num">Tồn trước</th>}
            <th class="num">Biến động</th>
          </tr>
        </thead>
        <tbody>
          {slip.items.map((i) => (
            <tr key={i.id}>
              <td>
                {i.bean_name}
                {i.note ? <div class="muted small">{i.note}</div> : null}
              </td>
              <td class="num">
                {/* Gõ bằng đơn vị quy đổi thì hiện ĐÚNG thứ đã gõ + số quy về đơn vị gốc */}
                {i.converted ? (
                  <>
                    {soVN(i.entered_qty)} <span class="muted small">{i.entered_unit}</span>
                    <div class="muted small">= {soVN(i.quantity)} {i.unit}</div>
                  </>
                ) : (
                  <>{soVN(i.quantity)} <span class="muted small">{i.unit}</span></>
                )}
              </td>
              {isAdj && <td class="num muted">{i.before_qty == null ? "—" : soVN(i.before_qty)}</td>}
              <td class={"num " + (i.delta > 0 ? "t-ok" : i.delta < 0 ? "t-danger" : "muted")}>
                {i.delta > 0 ? "+" : i.delta < 0 ? "−" : ""}{soVN(Math.abs(i.delta))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <a class="btn bean-more" href="#/kho-dau"><Icon name="box" size={15} /> Xem tồn kho đậu</a>
    </div>
  );
}
