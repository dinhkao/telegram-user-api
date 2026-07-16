// Popup GHI NHẬP KHO hàng mua về (từng đợt — như xuất kho cho đơn): mỗi dòng
// phiếu chọn 1 cách: tạo thùng mới (mặc định) / nhập vào thùng có sẵn (+tồn) /
// bỏ qua. Tạo thùng mới = như NHẬP THÙNG phiếu SX: chọn đơn vị chứa + SỐ THÙNG ×
// SỐ HÀNG/thùng → N thùng giống nhau. Prefill + trần = PHẦN CÒN LẠI trên phiếu
// (trừ phần đã nhập — draft_receipt). Submit → POST /receive-goods, KHÔNG chốt:
// gọi nhiều lần được; đủ rồi bấm 'Chốt nhập kho' ở trang phiếu. Cha mount khi mở.
import { useEffect, useState } from "preact/hooks";
import {
  allBoxes, listPlaces, listUnits, receivePurchaseGoods, soVN,
  type PurchaseSlip, type PurchaseDisposition, type KhoBox, type Place, type Unit,
} from "../api";
import { SelectPopup, type SPOption } from "../ui/SelectPopup";
import { confirmDialog, toast } from "../ui/feedback";
import { usePopupBack } from "../ui/usePopupBack";
import { useScrollLock } from "../useScrollLock";
import { Icon } from "../ui/Icon";

type Act = "restock_new" | "restock_existing" | "skip";
// restock_new: count (số thùng) × per (số hàng/thùng); restock_existing: qty cộng vào thùng.
// held/cap cố định từ lúc mở: held = số đã nằm trong thùng giữ lại (sau hủy chốt),
// cap = trần còn nhập được của dòng (= số trên phiếu − held) — server check cùng luật.
type Row = {
  sp: string; action: Act;
  qty: string; count: string; per: string;
  held: number; cap: number;
  box_id?: number; place_id?: number | null; unit_id?: number | null;
};

const ACTIONS: SPOption[] = [
  { value: "restock_new", label: "🆕 Tạo thùng mới" },
  { value: "restock_existing", label: "📦 Nhập vào thùng có sẵn" },
  { value: "skip", label: "Bỏ qua (không quản kho)" },
];

const num = (s: string) => parseFloat((s || "").replace(",", ".")) || 0;

const initialRows = (pu: PurchaseSlip): Row[] => {
  // Đã nhập bao nhiêu theo mã (thùng mới + cộng thùng có sẵn) → prefill phần còn lại
  const retained = new Map<string, number>();
  for (const t of pu.draft_receipt?.totals || []) {
    const code = (t.sp || "").toUpperCase();
    retained.set(code, (retained.get(code) || 0) + Number(t.quantity || 0));
  }
  return (pu.items || []).map((it) => {
    const conv = !!it.unit && (it.unit_factor || 0) > 0;
    const base = it.sl * (conv ? it.unit_factor! : 1);
    const code = (it.sp || "").toUpperCase();
    const already = Math.min(base, retained.get(code) || 0);
    retained.set(code, Math.max(0, (retained.get(code) || 0) - already));
    const left = Math.max(0, base - already);
    const keepConversion = already <= 1e-6 && conv;
    return {
      sp: it.sp,
      action: left > 1e-6 ? "restock_new" as Act : "skip" as Act,
      qty: String(left),
      count: keepConversion ? String(it.sl) : "1",
      per: keepConversion ? String(it.unit_factor) : String(left),
      held: already, cap: left,
    };
  });
};

export function PurchaseGoodsModal({ pu, onClose, onDone }: {
  pu: PurchaseSlip; onClose: () => void; onDone: (p: PurchaseSlip) => void;
}) {
  // Prefill từ dòng phiếu: có đơn vị nhập (Thùng ×30) → count = SL thùng, per = số
  // hàng/thùng (khớp phiếu). Không đơn vị quy đổi → 1 thùng chứa cả lô. Đều sửa được.
  const [rows, setRows] = useState<Row[]>(() => initialRows(pu));
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
  const countOf = (r: Row) => Math.floor(num(r.count)) || 0;
  const perOf = (r: Row) => num(r.per);
  const totalOf = (r: Row) => (r.action === "restock_new" ? countOf(r) * perOf(r) : num(r.qty));
  // Số hàng TRÊN PHIẾU của dòng (đơn vị gốc) = trần nhập kho — không được vượt.
  const baseOf = (i: number) => {
    const it = (pu.items || [])[i];
    if (!it) return 0;
    return it.sl * (it.unit && (it.unit_factor || 0) > 0 ? it.unit_factor! : 1);
  };
  const unitNameOf = (r: Row) => units.find((u) => u.id === r.unit_id)?.name || "Thùng";
  const splitCountOf = (r: Row) => {
    if (r.action !== "restock_new" || countOf(r) !== 1) return 0;
    const base = r.cap;   // chia theo phần CÒN nhập được (đã trừ thùng giữ lại)
    const per = perOf(r);
    if (base <= 0 || per <= 0 || per >= base - 1e-6) return 0;
    const ratio = base / per;
    const rounded = Math.round(ratio);
    return rounded > 1 && Math.abs(ratio - rounded) <= 1e-6 ? rounded : 0;
  };

  const missingBox = rows.some((r) => r.action === "restock_existing" && !r.box_id);
  const badNew = rows.some((r) => r.action === "restock_new" && (countOf(r) < 1 || perOf(r) <= 0));
  const badExisting = rows.some((r) => r.action === "restock_existing" && num(r.qty) <= 0);
  const overRows = rows.some((r) => r.action !== "skip" && totalOf(r) > r.cap + 1e-6);

  const submit = async () => {
    if (missingBox) { toast("Chọn thùng cho dòng ‘Nhập vào thùng có sẵn’", "err"); return; }
    if (badNew) { toast("Số thùng ≥ 1 và số hàng/thùng phải > 0", "err"); return; }
    if (badExisting) { toast("Số lượng thực nhận phải > 0 (hoặc chọn Bỏ qua)", "err"); return; }
    if (overRows) { toast("Tổng hàng nhập kho không được vượt số trên phiếu", "err"); return; }
    let submitRows = rows;
    const splitRows = rows
      .map((r, i) => ({ i, r, count: splitCountOf(r) }))
      .filter((x) => x.count > 1);
    if (splitRows.length) {
      const lines = splitRows.map(({ r, count }) =>
        `${r.sp}: ${count} ${unitNameOf(r).toLowerCase()} × ${soVN(perOf(r))}`);
      if (await confirmDialog(
        `Có dòng đang để 1 ${unitNameOf(splitRows[0].r).toLowerCase()} nhưng chia đều được theo số trên phiếu:\n${lines.join("\n")}`,
        { okLabel: "Tự chia", cancelLabel: "Giữ như hiện tại" },
      )) {
        const counts = Object.fromEntries(splitRows.map((x) => [x.i, String(x.count)]));
        submitRows = rows.map((r, i) => (counts[i] ? { ...r, count: counts[i] } : r));
        setRows(submitRows);
      }
    }

    const active = submitRows.filter((r) => r.action !== "skip");
    if (!active.length) {
      toast("Chưa chọn dòng nào để nhập — chọn cách nhập hoặc bấm Để sau", "info");
      return;
    }
    const dispositions: PurchaseDisposition[] = active.map((r) =>
      r.action === "restock_existing"
        ? { sp: r.sp, quantity: num(r.qty), action: r.action, box_id: r.box_id }
        : { sp: r.sp, quantity: perOf(r), count: countOf(r), action: r.action,
            place_id: r.place_id ?? null, unit_id: r.unit_id ?? null });
    const nBoxes = active.filter((r) => r.action === "restock_new").reduce((s, r) => s + countOf(r), 0);
    const nRe = active.filter((r) => r.action === "restock_existing").length;
    const parts: string[] = [];
    if (nBoxes) parts.push(`tạo ${nBoxes} thùng mới`);
    if (nRe) parts.push(`cộng ${nRe} thùng có sẵn`);
    if (!(await confirmDialog(
      `Ghi nhập kho: ${parts.join(", ")}?\n(Chưa chốt — xoá/gỡ/nhập thêm được, đủ rồi bấm Chốt nhập kho ở trang phiếu)`,
      { okLabel: "Ghi nhập" }))) return;
    setBusy(true);
    try {
      const { purchase: updated } = await receivePurchaseGoods(pu.id, dispositions);
      toast("Đã ghi nhập kho — kiểm tra rồi bấm Chốt nhập kho", "ok");
      onDone(updated);
    } catch (e: any) {
      toast(e?.message || "Lỗi nhập kho", "err");
    } finally { setBusy(false); }
  };

  return (
    <div class="modal-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="modal-sheet rg-sheet" onClick={(e: any) => e.stopPropagation()}>
        <div class="modal-head"><Icon name="box" size={16} /> Ghi nhập kho hàng mua về</div>
        <p class="muted small" style={{ margin: "0 0 4px" }}>
          Chọn cách nhập từng loại — ghi nhiều đợt được, đủ rồi bấm Chốt ở trang phiếu.
          Sửa SL nếu thực nhận lệch phiếu (thiếu/vỡ).
        </p>
        {rows.map((r, i) => {
          const item = (pu.items || [])[i];
          const baseUnit = item?.base_unit || "";
          const unitName = units.find((u) => u.id === r.unit_id)?.name || "Thùng";
          const conv = item?.unit && (item.unit_factor || 0) > 0
            ? `${soVN(item.sl)} ${item.unit} × ${soVN(item.unit_factor!)} = ${soVN(item.sl * item.unit_factor!)}${baseUnit ? ` ${baseUnit}` : ""}` : "";
          const bopts: SPOption[] = boxesOf(r.sp).map((b) => ({
            value: b.id, label: `Thùng ${b.box_code}`,
            sub: `còn ${soVN(b.remaining ?? b.quantity)}${b.place_name ? ` · ${b.place_name}` : ""}`,
          }));
          const total = totalOf(r);
          const base = baseOf(i);
          const over = r.action !== "skip" && total > r.cap + 1e-6;
          return (
            <div class="rg-row" key={i}>
              <div class="rg-row-head rg-qty-head">
                <b>{r.sp}</b>
                {r.action === "restock_existing" && (
                  <input class={"rg-qty-input" + (over ? " over" : "")} type="text" inputMode="decimal" value={r.qty}
                    onFocus={(e) => (e.target as HTMLInputElement).select()}
                    onInput={(e: any) => upd(i, { qty: e.currentTarget.value })} />
                )}
              </div>
              {r.action !== "skip" && (
                <div class={"muted small" + (over ? " pg-over" : "")}>
                  Số hàng trên phiếu: <b>{soVN(base)}{baseUnit ? ` ${baseUnit}` : ""}</b>
                  {conv ? ` (${conv})` : ""}
                  {r.held > 1e-6 ? ` · đã nhập ${soVN(r.held)} · còn nhập được ${soVN(r.cap)}` : ""}
                  {over ? " · ⚠ đang nhập vượt số còn lại" : ""}
                </div>
              )}
              <SelectPopup value={r.action} options={ACTIONS}
                onChange={(v) => upd(i, { action: v as Act, box_id: undefined })} />
              {r.action === "restock_existing" && (
                bopts.length
                  ? <SelectPopup value={r.box_id ?? ""} options={bopts} searchable placeholder="Chọn thùng để nhập vào…"
                      onChange={(v) => upd(i, { box_id: Number(v) })} />
                  : <div class="muted small">Chưa có thùng {r.sp} còn hàng — chọn “Tạo thùng mới”.</div>
              )}
              {r.action === "restock_new" && (
                <div class="pg-newbox">
                  <div class="rg-newbox">
                    <SelectPopup value={r.place_id ?? ""} placeholder="Vị trí kho"
                      options={[{ value: "", label: "(chưa xếp vị trí)" }, ...places.map((p) => ({ value: p.id, label: p.name }))]}
                      onChange={(v) => upd(i, { place_id: v ? Number(v) : null })} />
                    <SelectPopup value={r.unit_id ?? ""} placeholder="Đơn vị chứa"
                      options={[{ value: "", label: "(đơn vị mặc định)" }, ...units.map((u) => ({ value: u.id, label: u.name }))]}
                      onChange={(v) => upd(i, { unit_id: v ? Number(v) : null })} />
                  </div>
                  <div class="pg-qty-line">
                    <input type="text" inputMode="numeric" value={r.count}
                      onFocus={(e) => (e.target as HTMLInputElement).select()}
                      onInput={(e: any) => upd(i, { count: e.currentTarget.value })}
                      title={`Số ${unitName.toLowerCase()}`} />
                    <span class="pg-x">{unitName} ×</span>
                    <input type="text" inputMode="decimal" value={r.per}
                      onFocus={(e) => (e.target as HTMLInputElement).select()}
                      onInput={(e: any) => upd(i, { per: e.currentTarget.value })}
                      title={`Số hàng trong 1 ${unitName.toLowerCase()}`} placeholder={baseUnit ? `Số ${baseUnit}` : "Số hàng"} />
                    {baseUnit && <span class="pg-x">{baseUnit}</span>}
                  </div>
                  <div class={"muted small" + (over ? " pg-over" : "")}>
                    = {soVN(total)}{baseUnit ? ` ${baseUnit}` : ""} nhập kho ({countOf(r)} {unitName.toLowerCase()})
                    {" / "}{r.held > 1e-6 ? `còn nhập được ${soVN(r.cap)}` : `phiếu ${soVN(base)}`}
                  </div>
                </div>
              )}
            </div>
          );
        })}
        <div class="row" style={{ marginTop: "8px" }}>
          <button class="btn" onClick={onClose}>Để sau</button>
          <button class="btn primary" disabled={busy || overRows} onClick={submit}>{busy ? "Đang ghi…" : "Ghi nhập"}</button>
        </div>
      </div>
    </div>
  );
}
