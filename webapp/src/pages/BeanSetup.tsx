// THIẾT LẬP KHO ĐẬU (#/kho-dau/thiet-lap) — 2 danh mục: VỊ TRÍ KHO (Kho A, Kho B…)
// và LOẠI ĐẬU (tên + đơn vị chính). Thêm = nút mở POPUP (detail/BeanAddPopup), quy
// đổi đơn vị = nút ⇄ mở POPUP (detail/BeanUnits). Thêm = mọi user, sửa = văn phòng,
// xoá = admin (chặn khi còn phiếu). Realtime: bean_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import {
  currentUser, deleteBean, deleteBeanPlace, getBeanBoard, isOffice, soVN,
  updateBean, updateBeanPlace, type BeanBoardData,
} from "../api";
import { BeanAddPopup, type BeanAddMode } from "../detail/BeanAddPopup";
import { BeanUnits } from "../detail/BeanUnits";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { confirmDialog, promptDialog, toast } from "../ui/feedback";
import { ErrorState, SkeletonList } from "../ui/states";

export function BeanSetup() {
  const [data, setData] = useState<BeanBoardData | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState<BeanAddMode | null>(null);   // popup thêm kho / loại đậu
  const [unitsFor, setUnitsFor] = useState<number | null>(null);    // popup quy đổi đơn vị
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
  // Lấy lại từ data mỗi lần render → popup luôn thấy đơn vị mới nhất sau khi sửa.
  const unitsBean = data.beans.find((b) => b.id === unitsFor);

  return (
    <div class="bean-setup">
      <PageHead fallback="#/kho-dau" title={<><Icon name="settings" size={18} /> Thiết lập kho đậu</>}
        sub="Vị trí kho + danh mục đậu" />

      <div class="ie-head">
        Vị trí kho ({data.places.length})
        <button class="btn small primary bean-head-add" onClick={() => setAdding("place")}>
          <Icon name="plus" size={14} /> Thêm kho
        </button>
      </div>
      {!data.places.length && <p class="muted small">Chưa có kho nào — bấm "Thêm kho" để tạo Kho A, Kho B…</p>}
      {data.places.map((p) => (
        <div class="bean-row" key={p.id}>
          <div class="bean-row-main">
            <div class="bean-row-name"><Icon name="box" size={14} /> {p.name}</div>
            <div class="muted small">tồn {soVN(placeTotal(p.id))}{p.note ? ` · ${p.note}` : ""}</div>
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

      <div class="ie-head">
        Danh mục đậu ({data.beans.length})
        <button class="btn small primary bean-head-add" onClick={() => setAdding("bean")}>
          <Icon name="plus" size={14} /> Thêm loại đậu
        </button>
      </div>
      {!data.beans.length && <p class="muted small">Chưa có loại đậu nào.</p>}
      {data.beans.map((b) => (
        <div class="bean-row" key={b.id}>
          <div class="bean-row-main">
            <div class="bean-row-name">{b.name}</div>
            <div class="muted small">tồn {soVN(beanTotal(b.id))} {b.unit}</div>
          </div>
          <button class="btn small" title="Quy đổi đơn vị" onClick={() => setUnitsFor(b.id)}>
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
      ))}

      <p class="muted small bean-hint-foot">
        Nút ⇄ = khai đơn vị quy đổi (1 bao = 50 kg…) và đổi đơn vị chính.
        Xoá được khi loại đậu / kho chưa dính phiếu nào. Sửa tên = văn phòng, xoá = admin.
      </p>

      {adding && <BeanAddPopup mode={adding} onClose={() => setAdding(null)} onDone={load} />}
      {unitsBean && (
        <BeanUnits bean={unitsBean} onClose={() => setUnitsFor(null)} onChanged={load} />
      )}
    </div>
  );
}
