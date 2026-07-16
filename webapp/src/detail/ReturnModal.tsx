// Popup tạo phiếu TRẢ HÀNG cho khách (văn phòng) — dòng hàng: SP (autocomplete) ×
// SL × giá TRẢ (dương). Submit = confirm → POST /api/customers/{key}/returns
// (server tạo HĐ KiotViet GIÁ ÂM → trừ nợ). Cha (CustomerDetail) mount khi mở.
import { useState } from "preact/hooks";
import { createReturn, searchProducts, soVN } from "../api";
import { CustomerPicker } from "./CustomerPicker";
import { PickerPopup, type PickOpt } from "../ui/PickerPopup";
import { confirmDialog, toast } from "../ui/feedback";
import { usePopupBack } from "../ui/usePopupBack";
import { useScrollLock } from "../useScrollLock";
import { Icon } from "../ui/Icon";
import { parseMoney, parseQty } from "../format";

type Line = { sp: string; sl: string; price: string };

export function ReturnModal({ ckey, onClose, onCreated }: {
  ckey?: string;                 // thiếu → chọn khách ngay trong popup (mở từ dashboard)
  onClose: () => void;
  onCreated: () => void;
}) {
  const [pickedKey, setPickedKey] = useState<string>(ckey || "");
  const [lines, setLines] = useState<Line[]>([{ sp: "", sl: "1", price: "" }]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useScrollLock(true);
  usePopupBack(true, onClose);

  const upd = (i: number, patch: Partial<Line>) =>
    setLines((prev) => prev.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  const parsed = lines
    .map((l) => ({ sp: l.sp.trim().toUpperCase(), sl: parseQty(l.sl), price: parseMoney(l.price) }))
    .filter((l) => l.sp && isFinite(l.sl) && l.sl > 0 && isFinite(l.price) && l.price > 0);
  const total = parsed.reduce((s, l) => s + l.sl * l.price, 0);

  const submit = async () => {
    if (!pickedKey) return toast("Chọn khách hàng trước", "info");
    if (!parsed.length) return toast("Nhập ít nhất 1 dòng hàng trả (SP + SL + giá)", "info");
    if (!(await confirmDialog(`Tạo phiếu trả hàng −${soVN(total)}đ? (NHÁP — chưa trừ nợ; vào phiếu bấm 'Tạo HĐ KiotViet' mới trừ)`))) return;
    setBusy(true);
    try {
      const r = await createReturn(pickedKey, parsed, note.trim());
      toast("Đã tạo phiếu trả (nháp)", "ok");
      const rid = r?.return?.id;
      // Prompt: xử lý HÀNG trả về ngay? (nhập lại kho / xuất hủy) — mở modal ở trang chi tiết.
      if (rid && await confirmDialog("Xử lý hàng trả về ngay? (nhập lại kho hoặc xuất hủy)",
        { okLabel: "Xử lý ngay", cancelLabel: "Để sau" })) {
        sessionStorage.setItem("rg_open", String(rid));
      }
      onCreated();
      onClose();
      if (rid) window.location.hash = `#/tra-hang/${rid}`;
    } catch (e: any) {
      toast(e?.message || "Lỗi tạo phiếu trả", "err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div class="modal-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="modal-sheet ret-sheet" onClick={(e: any) => e.stopPropagation()}>
        <div class="modal-head"><Icon name="refresh" size={16} /> Trả hàng</div>
        {!ckey && <CustomerPicker placeholder="Chọn khách trả hàng" onPick={(c) => setPickedKey(c?.key || "")} />}
        {lines.map((l, i) => (
          <div class="ret-line" key={i}>
            <div class="ret-sp">
              <PickerPopup value={l.sp} placeholder="Mã SP" allowFreeText
                onSearch={async (q): Promise<PickOpt[]> =>
                  (await searchProducts(q).catch(() => [])).map((s) => ({ key: s.code, label: s.code, sub: s.name || undefined }))}
                onPick={(o) => upd(i, { sp: o.key })} />
            </div>
            <input class="ret-sl" type="text" inputMode="decimal" placeholder="SL" value={l.sl}
              onFocus={(e) => (e.target as HTMLInputElement).select()}
              onInput={(e) => upd(i, { sl: (e.target as HTMLInputElement).value })} />
            <input class="ret-price" type="text" inputMode="numeric" placeholder="Giá trả" value={l.price}
              onFocus={(e) => (e.target as HTMLInputElement).select()}
              onInput={(e) => upd(i, { price: (e.target as HTMLInputElement).value })} />
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
        <input type="text" placeholder="Ghi chú (tuỳ chọn)" value={note}
          onInput={(e) => setNote((e.target as HTMLInputElement).value)} />
        <div class="ret-total">Tổng trả: <b>−{soVN(total)}đ</b></div>
        <div class="row">
          <button class="btn" onClick={onClose}>Huỷ</button>
          <button class="btn primary" disabled={busy || !parsed.length} onClick={submit}>
            {busy ? "Đang tạo…" : "Tạo phiếu trả"}
          </button>
        </div>
      </div>
    </div>
  );
}
