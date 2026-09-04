// Chi tiết 1 KHO ĐẬU (#/kho-dau/kho/:id) — sửa ngay tại trang (tên · ghi chú, văn
// phòng), tồn từng loại đậu trong kho, phiếu gần đây của kho. Xoá = admin (chặn khi
// còn phiếu). Realtime: bean_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import {
  currentUser, deleteBeanPlace, getBeanPlaceDetail, isOffice, soVN, updateBeanPlace,
  type BeanPlaceDetailData,
} from "../api";
import { BeanSlipCard } from "../detail/BeanSlipRows";
import { History } from "../detail/History";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { confirmDialog, toast } from "../ui/feedback";
import { EmptyState, ErrorState, Loading } from "../ui/states";

export function BeanPlaceDetail({ id }: { id: string }) {
  const [data, setData] = useState<BeanPlaceDetailData | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ name: "", note: "" });
  const office = isOffice();
  const admin = currentUser()?.role === "admin";

  const load = () => getBeanPlaceDetail(id)
    .then((d) => { setData(d); setErr(""); })
    .catch((e: any) => setErr(e?.message || "Lỗi tải kho"));
  useEffect(() => { load(); }, [id]);
  useEffect(() => onRealtime((e) => {
    if (e.type === "bean_changed" || e.type === "resync") load();
  }), [id]);

  const startEdit = () => {
    if (!data) return;
    setForm({ name: data.place.name, note: data.place.note || "" });
    setEditing(true);
  };
  const save = async () => {
    if (!form.name.trim()) return toast("Tên không được rỗng", "err");
    setBusy(true);
    try {
      await updateBeanPlace(Number(id), { name: form.name.trim(), note: form.note.trim() });
      await load();
      setEditing(false);
      toast("Đã lưu", "ok");
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu", "err");
    } finally { setBusy(false); }
  };
  const del = async () => {
    if (!data) return;
    if (!(await confirmDialog(`Xoá kho "${data.place.name}"?`,
      { danger: true, okLabel: "Xoá kho" }))) return;
    setBusy(true);
    try {
      await deleteBeanPlace(Number(id));
      toast("Đã xoá kho", "ok");
      window.location.hash = "#/kho-dau/thiet-lap";
    } catch (e: any) {
      toast(e?.message || "Lỗi xoá", "err");
    } finally { setBusy(false); }
  };

  if (err) return <ErrorState msg={err} onRetry={() => { setErr(""); load(); }} />;
  if (!data) return <Loading />;
  const p = data.place;

  return (
    <div class="bean-detail">
      <PageHead fallback="#/kho-dau" title={<><Icon name="box" size={18} /> {p.name}</>}
        sub={<>Tồn <b>{soVN(data.total)}</b> · {data.by_bean.length} loại đậu
          {data.slip_count ? ` · ${data.slip_count} phiếu` : ""}</>}
        right={office && !editing ? (
          <button class="btn small" title="Sửa" onClick={startEdit}><Icon name="edit" size={15} /></button>
        ) : undefined} />

      {editing ? (
        <div class="bean-edit">
          <div class="bean-form-row">
            <label class="bean-lbl">Tên kho</label>
            <input class="bean-in" value={form.name}
              onInput={(e: any) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div class="bean-form-row">
            <label class="bean-lbl">Ghi chú</label>
            <input class="bean-in" value={form.note} placeholder="Tuỳ chọn"
              onInput={(e: any) => setForm({ ...form, note: e.target.value })} />
          </div>
          <div class="row">
            <button class="btn" disabled={busy} onClick={() => setEditing(false)}>Huỷ</button>
            <button class="btn primary" disabled={busy || !form.name.trim()} onClick={save}>
              {busy ? "Đang lưu…" : "Lưu"}
            </button>
          </div>
        </div>
      ) : (
        (p.note || p.created_by) && (
          <div class="bean-meta muted small">
            {p.note}{p.note && p.created_by ? " · " : ""}
            {p.created_by ? `tạo bởi ${p.created_by}` : ""}
          </div>
        )
      )}

      <div class="bean-actions">
        <a class="btn primary" href="#/kho-dau/tao?kind=nhap"><Icon name="plus" size={16} /> Nhập</a>
        <a class="btn" href="#/kho-dau/tao?kind=xuat"><Icon name="truck" size={16} /> Xuất</a>
        <a class="btn" href="#/kho-dau/tao?kind=dieu_chinh"><Icon name="edit" size={16} /> Điều chỉnh</a>
        <a class="btn" href="#/kho-dau/tao?kind=chuyen"><Icon name="refresh" size={16} /> Chuyển</a>
      </div>

      <div class="ie-head">Tồn trong kho</div>
      {data.by_bean.length ? data.by_bean.map((r) => (
        <a class="bean-row" href={`#/kho-dau/dau/${r.bean_id}`} key={r.bean_id}>
          <div class="bean-row-main">
            <div class="bean-row-name">{r.bean_name}</div>
          </div>
          <span class="bean-qty">{soVN(r.qty)} <span class="muted small">{r.unit}</span></span>
          <Icon name="chevronRight" size={18} class="kg-arrow" />
        </a>
      )) : <EmptyState>Kho trống.</EmptyState>}

      <div class="ie-head">
        Phiếu gần đây
        <a class="btn small bean-head-add" href="#/kho-dau/phieu">Tất cả phiếu</a>
      </div>
      {data.slips.length ? data.slips.map((s) => (
        <BeanSlipCard slip={s} showPlace={false} key={s.id} />
      )) : <EmptyState>Chưa có phiếu nào ở kho này.</EmptyState>}

      {/* Lịch sử riêng của kho (audit scope 'bean_place') — ảnh/trao đổi nằm ở PHIẾU */}
      <History base={`/api/media/bean_place/${id}`} />

      {admin && (
        <button class="btn danger bean-more" disabled={busy} onClick={del}>
          <Icon name="trash" size={15} /> Xoá kho
        </button>
      )}
    </div>
  );
}
