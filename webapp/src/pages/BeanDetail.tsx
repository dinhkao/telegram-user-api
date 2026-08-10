// Chi tiết 1 LOẠI ĐẬU (#/kho-dau/dau/:id) — sửa ngay tại trang (tên · đơn vị chính ·
// ghi chú, văn phòng), tồn chia theo kho, đơn vị quy đổi (popup detail/BeanUnits),
// phiếu gần đây có dính loại đậu này. Xoá = admin. Realtime: bean_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import {
  currentUser, deleteBean, getBeanDetail, isOffice, soVN, updateBean,
  type BeanDetailData,
} from "../api";
import { BeanSlipCard } from "../detail/BeanSlipRows";
import { BeanUnits } from "../detail/BeanUnits";
import { History } from "../detail/History";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { confirmDialog, toast } from "../ui/feedback";
import { EmptyState, ErrorState, Loading } from "../ui/states";

export function BeanDetail({ id }: { id: string }) {
  const [data, setData] = useState<BeanDetailData | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ name: "", unit: "", note: "" });
  const [showUnits, setShowUnits] = useState(false);
  const office = isOffice();
  const admin = currentUser()?.role === "admin";

  const load = () => getBeanDetail(id)
    .then((d) => { setData(d); setErr(""); })
    .catch((e: any) => setErr(e?.message || "Lỗi tải loại đậu"));
  useEffect(() => { load(); }, [id]);
  useEffect(() => onRealtime((e) => {
    if (e.type === "bean_changed" || e.type === "resync") load();
  }), [id]);

  const startEdit = () => {
    if (!data) return;
    setForm({ name: data.bean.name, unit: data.bean.unit, note: data.bean.note || "" });
    setEditing(true);
  };
  const save = async () => {
    if (!form.name.trim()) return toast("Tên không được rỗng", "err");
    setBusy(true);
    try {
      await updateBean(Number(id), { name: form.name.trim(), unit: form.unit.trim() || "kg",
                                     note: form.note.trim() });
      await load();
      setEditing(false);
      toast("Đã lưu", "ok");
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu", "err");
    } finally { setBusy(false); }
  };
  const del = async () => {
    if (!data) return;
    if (!(await confirmDialog(`Xoá loại đậu "${data.bean.name}"?`,
      { danger: true, okLabel: "Xoá loại đậu" }))) return;
    setBusy(true);
    try {
      await deleteBean(Number(id));
      toast("Đã xoá loại đậu", "ok");
      window.location.hash = "#/kho-dau/thiet-lap";
    } catch (e: any) {
      toast(e?.message || "Lỗi xoá", "err");
    } finally { setBusy(false); }
  };

  if (err) return <ErrorState msg={err} onRetry={() => { setErr(""); load(); }} />;
  if (!data) return <Loading />;
  const b = data.bean;
  const units = b.units || [];

  return (
    <div class="bean-detail">
      <PageHead fallback="#/kho-dau" title={b.name}
        sub={<>Tồn <b>{soVN(data.total)} {b.unit}</b>{data.slip_count ? ` · ${data.slip_count} phiếu` : ""}</>}
        right={office && !editing ? (
          <button class="btn small" title="Sửa" onClick={startEdit}><Icon name="edit" size={15} /></button>
        ) : undefined} />

      {editing ? (
        <div class="bean-edit">
          <div class="bean-form-row">
            <label class="bean-lbl">Tên</label>
            <input class="bean-in" value={form.name}
              onInput={(e: any) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div class="bean-form-row">
            <label class="bean-lbl">Đơn vị chính</label>
            <input class="bean-in" value={form.unit}
              onInput={(e: any) => setForm({ ...form, unit: e.target.value })} />
          </div>
          <p class="muted small">
            Sửa ở đây chỉ đổi CHỮ, mọi con số giữ nguyên. Muốn chuyển hẳn sang tính theo
            đơn vị khác (kg → bao, số tự quy đổi lại) thì dùng nút ★ trong ⇄ Quy đổi đơn vị.
          </p>
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
        <div class="bean-meta muted small">
          Đơn vị chính: <b>{b.unit}</b>
          {b.note ? <> · {b.note}</> : null}
          {b.created_by ? <> · tạo bởi {b.created_by}</> : null}
        </div>
      )}

      <div class="ie-head">
        Quy đổi đơn vị ({units.length})
        <button class="btn small bean-head-add" onClick={() => setShowUnits(true)}>⇄ Quản lý</button>
      </div>
      {units.length ? (
        <div class="bean-unit-chips">
          {units.map((u) => (
            <span class="chip" key={u.id}>1 {u.name} = {soVN(u.factor)} {b.unit}</span>
          ))}
        </div>
      ) : (
        <p class="muted small">Chưa khai đơn vị nào khác — chỉ nhập/xuất theo {b.unit}.</p>
      )}

      <div class="ie-head">Tồn theo kho</div>
      {data.by_place.length ? data.by_place.map((r) => (
        <a class="bean-row" href={`#/kho-dau/kho/${r.place_id}`} key={r.place_id}>
          <div class="bean-row-main">
            <div class="bean-row-name"><Icon name="box" size={14} /> {r.place_name}</div>
          </div>
          <span class="bean-qty">{soVN(r.qty)} <span class="muted small">{b.unit}</span></span>
          <Icon name="chevronRight" size={18} class="kg-arrow" />
        </a>
      )) : <EmptyState>Chưa có tồn ở kho nào.</EmptyState>}

      <div class="ie-head">
        Phiếu gần đây
        <a class="btn small bean-head-add" href="#/kho-dau/phieu">Tất cả phiếu</a>
      </div>
      {data.slips.length ? data.slips.map((s) => (
        <BeanSlipCard slip={s} showBean={false} key={s.id} />
      )) : <EmptyState>Chưa có phiếu nào cho loại đậu này.</EmptyState>}

      {/* Lịch sử riêng của loại đậu (audit scope 'bean_item') — ảnh/trao đổi nằm ở PHIẾU */}
      <History base={`/api/media/bean_item/${id}`} />

      {admin && (
        <button class="btn danger bean-more" disabled={busy} onClick={del}>
          <Icon name="trash" size={15} /> Xoá loại đậu
        </button>
      )}

      {showUnits && (
        <BeanUnits bean={b} onClose={() => setShowUnits(false)} onChanged={load} />
      )}
    </div>
  );
}
