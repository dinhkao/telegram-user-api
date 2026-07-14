// Popup XỬ LÝ HÀNG khách trả về — mỗi dòng hàng trả chọn 1 cách: nhập vào thùng có
// sẵn (+tồn) / tạo thùng mới / xuất hủy (box-less, không trừ tồn) / bỏ qua.
// Submit → POST /api/returns/{id}/handle-goods. Cha (ReturnDetail) mount khi mở.
import { useEffect, useState } from "preact/hooks";
import {
  allBoxes, listPlaces, listUnits, handleReturnGoods, soVN,
  type ReturnSlip, type ReturnDisposition, type KhoBox, type Place, type Unit,
} from "../api";
import { SelectPopup, type SPOption } from "../ui/SelectPopup";
import { confirmDialog, toast } from "../ui/feedback";
import { usePopupBack } from "../ui/usePopupBack";
import { useScrollLock } from "../useScrollLock";
import { Icon } from "../ui/Icon";

type Act = "restock_existing" | "restock_new" | "dispose" | "skip";
type Row = { sp: string; qty: number; action: Act; box_id?: number; place_id?: number | null; unit_id?: number | null };

const ACTIONS: SPOption[] = [
  { value: "restock_existing", label: "📦 Nhập vào thùng có sẵn" },
  { value: "restock_new", label: "🆕 Tạo thùng mới" },
  { value: "dispose", label: "🗑 Xuất hủy" },
  { value: "skip", label: "Bỏ qua" },
];

export function ReturnGoodsModal({ ret, onClose, onDone }: {
  ret: ReturnSlip; onClose: () => void; onDone: (r: ReturnSlip) => void;
}) {
  const [rows, setRows] = useState<Row[]>(
    (ret.items || []).map((it) => ({ sp: it.sp, qty: it.sl, action: "dispose" as Act })));
  const [boxes, setBoxes] = useState<KhoBox[]>([]);
  const [places, setPlaces] = useState<Place[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [busy, setBusy] = useState(false);
  useScrollLock(true);
  usePopupBack(true, onClose);

  useEffect(() => {
    allBoxes().then(setBoxes).catch(() => {});
    listPlaces().then(setPlaces).catch(() => {});
    listUnits().then(setUnits).catch(() => {});
  }, []);

  const upd = (i: number, patch: Partial<Row>) =>
    setRows((prev) => prev.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const boxesOf = (sp: string) =>
    boxes.filter((b) => !b.disabled && (b.remaining ?? b.quantity) > 0 && b.product_code.toUpperCase() === sp.toUpperCase());

  // "Nhập vào thùng có sẵn" bắt buộc chọn thùng trước khi xử lý.
  const missingBox = rows.some((r) => r.action === "restock_existing" && !r.box_id);

  const submit = async () => {
    if (missingBox) { toast("Chọn thùng cho dòng ‘Nhập vào thùng có sẵn’", "err"); return; }
    const active = rows.filter((r) => r.action !== "skip");
    if (!active.length) { onClose(); return; }
    const dispositions: ReturnDisposition[] = active.map((r) => ({
      sp: r.sp, quantity: r.qty, action: r.action,
      ...(r.action === "restock_existing" ? { box_id: r.box_id } : {}),
      ...(r.action === "restock_new" ? { place_id: r.place_id ?? null, unit_id: r.unit_id ?? null } : {}),
    }));
    const nRe = active.filter((r) => r.action === "restock_existing").length;
    const nRn = active.filter((r) => r.action === "restock_new").length;
    const nD = active.filter((r) => r.action === "dispose").length;
    const parts: string[] = [];
    if (nRe) parts.push(`nhập ${nRe} thùng có sẵn`);
    if (nRn) parts.push(`tạo ${nRn} thùng mới`);
    if (nD) parts.push(`xuất hủy ${nD} mục`);
    if (!(await confirmDialog(`Xử lý hàng trả: ${parts.join(", ")}?`, { okLabel: "Xử lý" }))) return;
    setBusy(true);
    try {
      const { return: updated } = await handleReturnGoods(ret.id, dispositions);
      toast("Đã xử lý hàng trả về", "ok");
      onDone(updated);
    } catch (e: any) {
      toast(e?.message || "Lỗi xử lý hàng trả", "err");
    } finally { setBusy(false); }
  };

  return (
    <div class="modal-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="modal-sheet rg-sheet" onClick={(e: any) => e.stopPropagation()}>
        <div class="modal-head"><Icon name="box" size={16} /> Xử lý hàng trả về</div>
        <p class="muted small" style={{ margin: "0 0 4px" }}>
          Khách trả hàng — chọn cách xử lý từng loại: nhập lại kho (thùng có sẵn / thùng mới) hay xuất hủy.
        </p>
        {rows.map((r, i) => {
          const bopts: SPOption[] = boxesOf(r.sp).map((b) => ({
            value: b.id, label: `Thùng ${b.box_code}`,
            sub: `còn ${soVN(b.remaining ?? b.quantity)}${b.place_name ? ` · ${b.place_name}` : ""}`,
          }));
          return (
            <div class="rg-row" key={i}>
              <div class="rg-row-head"><b>{r.sp}</b> <span class="muted">×{soVN(r.qty)}</span></div>
              <SelectPopup value={r.action} options={ACTIONS}
                onChange={(v) => upd(i, { action: v as Act, box_id: undefined })} />
              {r.action === "restock_existing" && (
                bopts.length
                  ? <SelectPopup value={r.box_id ?? ""} options={bopts} searchable placeholder="Chọn thùng để nhập vào…"
                      onChange={(v) => upd(i, { box_id: Number(v) })} />
                  : <div class="muted small">Chưa có thùng {r.sp} còn hàng — chọn “Tạo thùng mới”.</div>
              )}
              {r.action === "restock_new" && (
                <div class="rg-newbox">
                  <SelectPopup value={r.place_id ?? ""} placeholder="Vị trí kho"
                    options={[{ value: "", label: "(chưa xếp vị trí)" }, ...places.map((p) => ({ value: p.id, label: p.name }))]}
                    onChange={(v) => upd(i, { place_id: v ? Number(v) : null })} />
                  <SelectPopup value={r.unit_id ?? ""} placeholder="Đơn vị chứa"
                    options={[{ value: "", label: "(đơn vị mặc định)" }, ...units.map((u) => ({ value: u.id, label: u.name }))]}
                    onChange={(v) => upd(i, { unit_id: v ? Number(v) : null })} />
                </div>
              )}
            </div>
          );
        })}
        <div class="row" style={{ marginTop: "8px" }}>
          <button class="btn" onClick={onClose}>Để sau</button>
          <button class="btn primary" disabled={busy} onClick={submit}>{busy ? "Đang xử lý…" : "Xử lý"}</button>
        </div>
      </div>
    </div>
  );
}
