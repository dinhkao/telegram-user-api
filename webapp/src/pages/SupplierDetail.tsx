// Chi tiết NHÀ CUNG CẤP (#/ncc/:id) — thông tin (văn phòng sửa) + mọi phiếu nhập
// của NCC + tạo phiếu nhập ngay tại đây; ảnh + trao đổi + lịch sử dùng entity
// media scope 'supplier'. Xoá = admin (server chặn nếu còn phiếu nhập).
import { useEffect, useState } from "preact/hooks";
import { PageHead } from "../ui/PageHead";
import { fmtDateTimeVN } from "../format";
import {
  getSupplier, updateSupplier, deleteSupplier, currentUser, isOffice, soVN,
  type Supplier, type PurchaseSlip,
} from "../api";
import { onRealtime } from "../realtime";
import { Images } from "../detail/Images";
import { Comments } from "../detail/Comments";
import { History } from "../detail/History";
import { confirmDialog, toast } from "../ui/feedback";
import { Loading, ErrorState } from "../ui/states";
import { Icon } from "../ui/Icon";

export function SupplierDetail({ id }: { id: string }) {
  const [s, setS] = useState<Supplier | null>(null);
  const [purchases, setPurchases] = useState<PurchaseSlip[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ name: "", phone: "", address: "", note: "" });
  const isAdmin = currentUser()?.role === "admin";
  const office = isOffice();

  const load = () => getSupplier(id)
    .then((r) => { setS(r.supplier); setPurchases(r.purchases); })
    .catch((e: any) => setErr(e?.message || "Lỗi tải NCC"));
  useEffect(() => { load(); }, [id]);
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      const hit = e.type === "resync" || e.type === "purchase_changed" ||
        (e.type === "supplier_changed" && (!e.id || e.id === String(id)));
      if (hit) { clearTimeout(t); t = setTimeout(load, 250); }
    });
    return () => { off(); clearTimeout(t); };
  }, [id]);

  if (err) return <ErrorState msg={err} onRetry={load} />;
  if (!s) return <Loading />;
  const deleted = !!s.deleted_at;
  const total = purchases.reduce((sum, p) => sum + (p.total || 0), 0);

  const startEdit = () => {
    if (!office) return toast("Chỉ văn phòng mới được sửa nhà cung cấp", "info");
    setForm({ name: s.name || "", phone: s.phone || "", address: s.address || "", note: s.note || "" });
    setEditing(true);
  };
  const saveEdit = async () => {
    if (!form.name.trim()) return toast("Tên NCC không được rỗng", "info");
    setBusy(true);
    try {
      await updateSupplier(Number(id), {
        name: form.name.trim(), phone: form.phone.trim(),
        address: form.address.trim(), note: form.note.trim(),
      });
      toast("Đã lưu nhà cung cấp", "ok");
      setEditing(false);
      load();
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu", "err");
    } finally { setBusy(false); }
  };

  const doDelete = async () => {
    if (!isAdmin) return toast("Chỉ admin mới được xoá nhà cung cấp", "info");
    if (purchases.length) return toast("NCC còn phiếu nhập — xoá các phiếu nhập trước", "info");
    if (!(await confirmDialog(`Xoá nhà cung cấp "${s.name}"?`, { danger: true, okLabel: "Xoá NCC" }))) return;
    setBusy(true);
    try {
      await deleteSupplier(Number(id));
      toast("Đã xoá nhà cung cấp", "ok");
      window.location.hash = "#/ncc";
    } catch (e: any) {
      toast(e?.message || "Lỗi xoá NCC", "err");
    } finally { setBusy(false); }
  };

  const inp = (k: keyof typeof form, ph: string, type = "text") => (
    <input type={type} placeholder={ph} value={form[k]}
      onInput={(e) => setForm((f) => ({ ...f, [k]: (e.target as HTMLInputElement).value }))} />
  );

  return (
    <div class="ret-detail">
      <PageHead fallback="#/ncc"
        title={<><Icon name="users" size={18} /> {s.name}</>}
        sub={purchases.length ? `${purchases.length} phiếu nhập · tổng ${soVN(total)}đ` : "Chưa có phiếu nhập"} />
      {deleted && <div class="error-banner">NCC đã bị xoá{s.deleted_by ? ` bởi ${s.deleted_by}` : ""}</div>}

      <section class="card">
        <label class="card-label"><Icon name="info" size={15} /> Thông tin
          {!editing && !deleted && (
            <button class={"btn small ret-edit" + (office ? "" : " faded")} onClick={startEdit}>
              <Icon name="edit" size={13} /> Sửa
            </button>
          )}
        </label>
        {!editing ? (
          <div class="sup-info">
            {s.phone && <div><Icon name="phone" size={13} /> <a href={`tel:${s.phone}`}>{s.phone}</a></div>}
            {s.address && <div><Icon name="location" size={13} /> {s.address}</div>}
            {s.note && <div class="ret-card-note"><Icon name="note" size={13} /> {s.note}</div>}
            {!s.phone && !s.address && !s.note && <div class="muted small">Chưa có thông tin — bấm Sửa để thêm.</div>}
          </div>
        ) : (
          <div class="ret-sheet">
            {inp("name", "Tên nhà cung cấp *")}
            {inp("phone", "Số điện thoại", "tel")}
            {inp("address", "Địa chỉ")}
            {inp("note", "Ghi chú")}
            <div class="row">
              <button class="btn" onClick={() => setEditing(false)}>Huỷ</button>
              <button class="btn primary" disabled={busy || !form.name.trim()} onClick={saveEdit}>
                {busy ? "Đang lưu…" : "Lưu"}
              </button>
            </div>
          </div>
        )}
      </section>

      <section class="card">
        <label class="card-label"><Icon name="truck" size={15} /> Phiếu nhập hàng
          {!deleted && (
            <button class="btn small ret-edit"
              onClick={() => { window.location.hash = `#/nhap-hang/tao?ncc=${id}`; }}>
              <Icon name="plus" size={13} /> Tạo phiếu
            </button>
          )}
        </label>
        {!purchases.length && <div class="muted small">Chưa có phiếu nhập nào.</div>}
        {purchases.map((p) => (
          <a class="ret-card pur-card" href={`#/nhap-hang/${p.id}`} key={p.id}>
            <div class="ret-card-top">
              <span class="ret-cust">
                {p.created_at ? fmtDateTimeVN(p.created_at) : `Phiếu #${p.id}`}
              </span>
              <span class="pur-amt">+{soVN(p.total)}</span>
            </div>
            <div class="ret-card-sub muted small">
              {(p.items || []).map((x) => `${x.sp} ×${soVN(x.sl)}`).join(", ")}
              {p.created_by ? ` · ${p.created_by}` : ""}
            </div>
          </a>
        ))}
      </section>

      <Images base={`/api/media/supplier/${id}`} />
      <Comments base={`/api/media/supplier/${id}`} />
      <History base={`/api/media/supplier/${id}`} />

      {!deleted && (
        <button class={"btn danger block" + (isAdmin && !purchases.length ? "" : " faded")} disabled={busy} onClick={doDelete}
          title={purchases.length ? "Xoá các phiếu nhập trước" : undefined}>
          <Icon name="trash" size={15} /> {busy ? "Đang xoá…" : "Xoá nhà cung cấp"}
        </button>
      )}
    </div>
  );
}
