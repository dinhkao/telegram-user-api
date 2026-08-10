// THIẾT LẬP KHO ĐẬU (#/kho-dau/thiet-lap) — 2 danh mục: VỊ TRÍ KHO (Kho A, Kho B…)
// và LOẠI ĐẬU (tên + đơn vị). Thêm = mọi user, sửa = văn phòng, xoá = admin (chặn
// khi còn phiếu). Realtime: bean_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import {
  createBean, createBeanPlace, currentUser, deleteBean, deleteBeanPlace, getBeanBoard,
  isOffice, soVN, updateBean, updateBeanPlace, type BeanBoardData,
} from "../api";
import { BeanUnits } from "../detail/BeanUnits";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { confirmDialog, promptDialog, toast } from "../ui/feedback";
import { ErrorState, SkeletonList } from "../ui/states";

export function BeanSetup() {
  const [data, setData] = useState<BeanBoardData | null>(null);
  const [err, setErr] = useState("");
  const [newPlace, setNewPlace] = useState("");
  const [newBean, setNewBean] = useState("");
  const [newUnit, setNewUnit] = useState("kg");
  const [busy, setBusy] = useState(false);
  const [openUnits, setOpenUnits] = useState<number | null>(null);   // loại đậu đang mở khối quy đổi
  const office = isOffice();
  const admin = currentUser()?.role === "admin";

  const load = () => getBeanBoard()
    .then((d) => { setData(d); setErr(""); })
    .catch((e: any) => setErr(e?.message || "Lỗi tải kho đậu"));
  useEffect(() => { load(); }, []);
  useEffect(() => onRealtime((e) => {
    if (e.type === "bean_changed" || e.type === "resync") load();
  }), []);

  const run = async (fn: () => Promise<any>, okMsg: string) => {
    setBusy(true);
    try { await fn(); await load(); toast(okMsg, "ok"); }
    catch (e: any) { toast(e?.message || "Lỗi", "err"); }
    finally { setBusy(false); }
  };

  const addPlace = () => {
    const name = newPlace.trim();
    if (!name) return;
    run(async () => { await createBeanPlace(name); setNewPlace(""); }, "Đã thêm kho");
  };
  const addBean = () => {
    const name = newBean.trim();
    if (!name) return;
    run(async () => { await createBean(name, newUnit.trim() || "kg"); setNewBean(""); }, "Đã thêm loại đậu");
  };

  const renamePlace = async (id: number, cur: string) => {
    const name = await promptDialog("Tên kho", { initial: cur, okLabel: "Lưu" });
    if (name === null || !name.trim() || name.trim() === cur) return;
    run(() => updateBeanPlace(id, { name: name.trim() }), "Đã đổi tên kho");
  };
  const renameBean = async (id: number, cur: string, unit: string) => {
    const name = await promptDialog("Tên loại đậu", { initial: cur, okLabel: "Lưu" });
    if (name === null || !name.trim() || name.trim() === cur) return;
    run(() => updateBean(id, { name: name.trim(), unit }), "Đã đổi tên loại đậu");
  };
  const editUnit = async (id: number, cur: string) => {
    const unit = await promptDialog("Đơn vị tính (kg, bao, thùng…)", { initial: cur, okLabel: "Lưu" });
    if (unit === null || !unit.trim() || unit.trim() === cur) return;
    run(() => updateBean(id, { unit: unit.trim() }), "Đã đổi đơn vị");
  };

  const delPlace = async (id: number, name: string) => {
    if (!(await confirmDialog(`Xoá kho "${name}"?`, { danger: true, okLabel: "Xoá kho" }))) return;
    run(() => deleteBeanPlace(id), "Đã xoá kho");
  };
  const delBean = async (id: number, name: string) => {
    if (!(await confirmDialog(`Xoá loại đậu "${name}"?`, { danger: true, okLabel: "Xoá loại đậu" }))) return;
    run(() => deleteBean(id), "Đã xoá loại đậu");
  };

  if (err && !data) return <ErrorState msg={err} onRetry={() => { setErr(""); load(); }} />;
  if (!data) return <SkeletonList />;

  const beanTotal = (id: number) => data.by_bean.find((b) => b.id === id)?.total || 0;
  const placeTotal = (id: number) => data.by_place.find((p) => p.id === id)?.total || 0;

  return (
    <div class="bean-setup">
      <PageHead fallback="#/kho-dau" title={<><Icon name="settings" size={18} /> Thiết lập kho đậu</>}
        sub="Vị trí kho + danh mục đậu" />

      <div class="ie-head">Vị trí kho ({data.places.length})</div>
      <div class="row bean-add">
        <input class="bean-in" placeholder="Tên kho mới (vd Kho A)" value={newPlace}
          onInput={(e: any) => setNewPlace(e.target.value)}
          onKeyDown={(e: any) => { if (e.key === "Enter") addPlace(); }} />
        <button class="btn primary" disabled={busy || !newPlace.trim()} onClick={addPlace}>
          <Icon name="plus" size={16} />
        </button>
      </div>
      {!data.places.length && <p class="muted small">Chưa có kho nào — thêm Kho A, Kho B…</p>}
      {data.places.map((p) => (
        <div class="bean-row" key={p.id}>
          <div class="bean-row-main">
            <div class="bean-row-name"><Icon name="box" size={14} /> {p.name}</div>
            <div class="muted small">tồn {soVN(placeTotal(p.id))}</div>
          </div>
          {office && (
            <button class="btn small" title="Đổi tên" disabled={busy}
              onClick={() => renamePlace(p.id, p.name)}><Icon name="edit" size={14} /></button>
          )}
          {admin && (
            <button class="btn small danger" title="Xoá" disabled={busy}
              onClick={() => delPlace(p.id, p.name)}><Icon name="trash" size={14} /></button>
          )}
        </div>
      ))}

      <div class="ie-head">Danh mục đậu ({data.beans.length})</div>
      <div class="row bean-add">
        <input class="bean-in" placeholder="Tên loại đậu (vd Đậu xanh)" value={newBean}
          onInput={(e: any) => setNewBean(e.target.value)}
          onKeyDown={(e: any) => { if (e.key === "Enter") addBean(); }} />
        <input class="bean-in bean-unit-in" placeholder="Đơn vị" value={newUnit}
          onInput={(e: any) => setNewUnit(e.target.value)} />
        <button class="btn primary" disabled={busy || !newBean.trim()} onClick={addBean}>
          <Icon name="plus" size={16} />
        </button>
      </div>
      {!data.beans.length && <p class="muted small">Chưa có loại đậu nào.</p>}
      {data.beans.map((b) => (
        <div class="bean-row-wrap" key={b.id}>
          <div class="bean-row">
            <div class="bean-row-main">
              <div class="bean-row-name">{b.name}</div>
              <div class="muted small">
                tồn {soVN(beanTotal(b.id))} ·{" "}
                {office
                  ? <button class="bean-link" onClick={() => editUnit(b.id, b.unit)}>đơn vị: {b.unit}</button>
                  : <>đơn vị: {b.unit}</>}
              </div>
            </div>
            <button class={"btn small" + (openUnits === b.id ? " primary" : "")}
              title="Quy đổi đơn vị" onClick={() => setOpenUnits(openUnits === b.id ? null : b.id)}>
              ⇄ {(b.units || []).length || ""}
            </button>
            {office && (
              <button class="btn small" title="Đổi tên" disabled={busy}
                onClick={() => renameBean(b.id, b.name, b.unit)}><Icon name="edit" size={14} /></button>
            )}
            {admin && (
              <button class="btn small danger" title="Xoá" disabled={busy}
                onClick={() => delBean(b.id, b.name)}><Icon name="trash" size={14} /></button>
            )}
          </div>
          {openUnits === b.id && <BeanUnits bean={b} onChanged={load} />}
        </div>
      ))}

      <p class="muted small bean-hint-foot">
        Xoá được khi loại đậu / kho chưa dính phiếu nào. Sửa tên = văn phòng, xoá = admin.
      </p>
    </div>
  );
}
