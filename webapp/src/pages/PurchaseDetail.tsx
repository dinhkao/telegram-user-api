// Chi tiết phiếu NHẬP HÀNG (#/nhap-hang/:id) — giống trang đơn/phiếu trả nhưng
// 100% local (không KiotViet): văn phòng sửa hàng nhập/ghi chú thoải mái; ảnh +
// trao đổi + lịch sử dùng entity media scope 'purchase'. Xoá = admin (xoá mềm).
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import {
  getPurchase, deletePurchase, updatePurchase, searchProducts,
  currentUser, isOffice, soVN, type PurchaseSlip,
} from "../api";
import { onRealtime } from "../realtime";
import { Images } from "../detail/Images";
import { Comments } from "../detail/Comments";
import { History } from "../detail/History";
import { PickerPopup, type PickOpt } from "../ui/PickerPopup";
import { confirmDialog, toast } from "../ui/feedback";
import { Loading, ErrorState } from "../ui/states";
import { Icon } from "../ui/Icon";

type Line = { sp: string; sl: string; price: string };

export function PurchaseDetail({ id }: { id: string }) {
  const [r, setR] = useState<PurchaseSlip | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [lines, setLines] = useState<Line[]>([]);
  const [note, setNote] = useState("");
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

  const startEdit = () => {
    if (!office) return toast("Chỉ văn phòng mới được sửa phiếu nhập", "info");
    setLines((r.items || []).map((x) => ({ sp: x.sp, sl: String(x.sl), price: String(x.price) })));
    setNote(r.note || "");
    setEditing(true);
  };
  const updLine = (i: number, patch: Partial<Line>) =>
    setLines((prev) => prev.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  const parsed = lines
    .map((l) => ({ sp: l.sp.trim().toUpperCase(), sl: parseFloat(l.sl.replace(",", ".")), price: parseFloat(l.price.replace(/\./g, "").replace(",", ".")) }))
    .filter((l) => l.sp && isFinite(l.sl) && l.sl > 0 && isFinite(l.price) && l.price >= 0);
  const editTotal = parsed.reduce((s, l) => s + l.sl * l.price, 0);

  const saveEdit = async () => {
    if (!parsed.length) return toast("Cần ít nhất 1 dòng hàng hợp lệ", "info");
    setBusy(true);
    try {
      await updatePurchase(Number(id), parsed, note.trim());
      toast("Đã lưu phiếu nhập", "ok");
      setEditing(false);
      load();
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu", "err");
    } finally { setBusy(false); }
  };

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
          {!editing && !deleted && (
            <button class={"btn small ret-edit" + (office ? "" : " faded")} onClick={startEdit}>
              <Icon name="edit" size={13} /> Sửa
            </button>
          )}
        </label>
        {!editing ? (
          <>
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
          </>
        ) : (
          <div class="ret-sheet">
            {lines.map((l, i) => (
              <div class="ret-line" key={i}>
                <div class="ret-sp">
                  <PickerPopup value={l.sp} placeholder="Mã SP" allowFreeText
                    onSearch={async (q): Promise<PickOpt[]> =>
                      (await searchProducts(q).catch(() => []))
                        .filter((s) => s.can_purchase !== false)   // chỉ SP "có thể nhập"
                        .map((s) => ({ key: s.code, label: s.code, sub: s.name || undefined }))}
                    onPick={(o) => updLine(i, { sp: o.key })} />
                </div>
                <input class="ret-sl" type="text" inputMode="decimal" value={l.sl}
                  onFocus={(e) => (e.target as HTMLInputElement).select()}
                  onInput={(e) => updLine(i, { sl: (e.target as HTMLInputElement).value })} />
                <input class="ret-price" type="text" inputMode="numeric" value={l.price}
                  onFocus={(e) => (e.target as HTMLInputElement).select()}
                  onInput={(e) => updLine(i, { price: (e.target as HTMLInputElement).value })} />
                {lines.length > 1 && (
                  <button class="btn small" onClick={() => setLines((prev) => prev.filter((_, j) => j !== i))}>
                    <Icon name="close" size={14} />
                  </button>
                )}
              </div>
            ))}
            <button class="btn small" onClick={() => setLines((prev) => [...prev, { sp: "", sl: "1", price: "" }])}>
              <Icon name="plus" size={14} /> Thêm dòng
            </button>
            <input type="text" placeholder="Ghi chú" value={note} onInput={(e) => setNote((e.target as HTMLInputElement).value)} />
            <div class="ret-total">Tổng nhập: <b>{soVN(editTotal)}đ</b></div>
            <div class="row">
              <button class="btn" onClick={() => setEditing(false)}>Huỷ</button>
              <button class="btn primary" disabled={busy || !parsed.length} onClick={saveEdit}>
                {busy ? "Đang lưu…" : "Lưu"}
              </button>
            </div>
          </div>
        )}
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
