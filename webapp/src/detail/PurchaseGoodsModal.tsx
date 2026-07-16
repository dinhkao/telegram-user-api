// Popup NHẬP KHO hàng mua về — mỗi dòng phiếu nhập chọn 1 cách: tạo thùng mới
// (mặc định) / nhập vào thùng có sẵn (+tồn) / bỏ qua (hàng không quản kho).
// SL sửa được = số THỰC NHẬN (hàng về có thể thiếu/vỡ so với phiếu).
// Submit → POST /api/purchases/{id}/handle-goods (1 lần/phiếu). Cha mount khi mở.
import { useEffect, useState } from "preact/hooks";
import {
  allBoxes, listPlaces, listUnits, handlePurchaseGoods, soVN,
  type PurchaseSlip, type PurchaseDisposition, type KhoBox, type Place, type Unit,
} from "../api";
import { SelectPopup, type SPOption } from "../ui/SelectPopup";
import { confirmDialog, toast } from "../ui/feedback";
import { usePopupBack } from "../ui/usePopupBack";
import { useScrollLock } from "../useScrollLock";
import { Icon } from "../ui/Icon";

type Act = "restock_new" | "restock_existing" | "skip";
type Row = { sp: string; qty: string; action: Act; box_id?: number; place_id?: number | null; unit_id?: number | null };

const ACTIONS: SPOption[] = [
  { value: "restock_new", label: "🆕 Tạo thùng mới" },
  { value: "restock_existing", label: "📦 Nhập vào thùng có sẵn" },
  { value: "skip", label: "Bỏ qua (không quản kho)" },
];

export function PurchaseGoodsModal({ pu, onClose, onDone }: {
  pu: PurchaseSlip; onClose: () => void; onDone: (p: PurchaseSlip) => void;
}) {
  const [rows, setRows] = useState<Row[]>(
    (pu.items || []).map((it) => ({ sp: it.sp, qty: String(it.sl), action: "restock_new" as Act })));
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
  const qtyOf = (r: Row) => parseFloat(r.qty.replace(",", ".")) || 0;

  const missingBox = rows.some((r) => r.action === "restock_existing" && !r.box_id);
  const badQty = rows.some((r) => r.action !== "skip" && qtyOf(r) <= 0);

  const submit = async () => {
    if (missingBox) { toast("Chọn thùng cho dòng ‘Nhập vào thùng có sẵn’", "err"); return; }
    if (badQty) { toast("Số lượng thực nhận phải > 0 (hoặc chọn Bỏ qua)", "err"); return; }
    const active = rows.filter((r) => r.action !== "skip");
    if (!active.length) { onClose(); return; }
    const dispositions: PurchaseDisposition[] = active.map((r) => ({
      sp: r.sp, quantity: qtyOf(r), action: r.action,
      ...(r.action === "restock_existing" ? { box_id: r.box_id } : {}),
      ...(r.action === "restock_new" ? { place_id: r.place_id ?? null, unit_id: r.unit_id ?? null } : {}),
    }));
    const nRn = active.filter((r) => r.action === "restock_new").length;
    const nRe = active.filter((r) => r.action === "restock_existing").length;
    const parts: string[] = [];
    if (nRn) parts.push(`tạo ${nRn} thùng mới`);
    if (nRe) parts.push(`nhập ${nRe} thùng có sẵn`);
    if (!(await confirmDialog(`Nhập kho hàng mua: ${parts.join(", ")}? (1 lần/phiếu — sau đó phiếu khoá sửa)`, { okLabel: "Nhập kho" }))) return;
    setBusy(true);
    try {
      const { purchase: updated } = await handlePurchaseGoods(pu.id, dispositions);
      toast("Đã nhập kho hàng mua về", "ok");
      onDone(updated);
    } catch (e: any) {
      toast(e?.message || "Lỗi nhập kho", "err");
    } finally { setBusy(false); }
  };

  return (
    <div class="modal-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="modal-sheet rg-sheet" onClick={(e: any) => e.stopPropagation()}>
        <div class="modal-head"><Icon name="box" size={16} /> Nhập kho hàng mua về</div>
        <p class="muted small" style={{ margin: "0 0 4px" }}>
          Hàng về từ NCC — chọn cách nhập từng loại. Sửa SL nếu thực nhận lệch phiếu (thiếu/vỡ).
        </p>
        {rows.map((r, i) => {
          const bopts: SPOption[] = boxesOf(r.sp).map((b) => ({
            value: b.id, label: `Thùng ${b.box_code}`,
            sub: `còn ${soVN(b.remaining ?? b.quantity)}${b.place_name ? ` · ${b.place_name}` : ""}`,
          }));
          return (
            <div class="rg-row" key={i}>
              <div class="rg-row-head rg-qty-head">
                <b>{r.sp}</b>
                {r.action !== "skip" && (
                  <input class="rg-qty-input" type="text" inputMode="decimal" value={r.qty}
                    onFocus={(e) => (e.target as HTMLInputElement).select()}
                    onInput={(e: any) => upd(i, { qty: e.currentTarget.value })} />
                )}
              </div>
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
          <button class="btn primary" disabled={busy} onClick={submit}>{busy ? "Đang nhập…" : "Nhập kho"}</button>
        </div>
      </div>
    </div>
  );
}
