// Popup tạo phiếu NHẬP HÀNG (văn phòng) — chọn NCC (autocomplete, gõ tên lạ →
// tạo NCC mới ngay), dòng hàng: SP (autocomplete, dùng chung bảng sản phẩm) ×
// SL × giá nhập. 100% local, không đụng KiotViet. POST /api/purchases.
import { useState } from "preact/hooks";
import { createPurchase, createSupplier, listSuppliers, searchProducts, soVN, type Supplier } from "../api";
import { foldVN } from "../format";
import { PickerPopup, type PickOpt } from "../ui/PickerPopup";
import { confirmDialog, toast } from "../ui/feedback";
import { usePopupBack } from "../ui/usePopupBack";
import { useScrollLock } from "../useScrollLock";
import { Icon } from "../ui/Icon";

type Line = { sp: string; sl: string; price: string };
const NEW_PREFIX = "__new__:";

export function PurchaseModal({ supplierId, supplierName, onClose, onCreated }: {
  supplierId?: number;           // thiếu → chọn NCC ngay trong popup (mở từ dashboard)
  supplierName?: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [picked, setPicked] = useState<{ id: number; name: string } | null>(
    supplierId ? { id: supplierId, name: supplierName || `NCC #${supplierId}` } : null);
  const [lines, setLines] = useState<Line[]>([{ sp: "", sl: "1", price: "" }]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useScrollLock(true);
  usePopupBack(true, onClose);

  const searchSuppliers = async (q: string): Promise<PickOpt[]> => {
    const all: Supplier[] = await listSuppliers().catch(() => []);
    const fq = foldVN(q.trim());
    const hit = !fq ? all : all.filter((s) => foldVN(`${s.name} ${s.phone || ""}`).includes(fq));
    const opts: PickOpt[] = hit.map((s) => ({ key: String(s.id), label: s.name, sub: s.phone || undefined }));
    // gõ tên chưa có → cho tạo NCC mới ngay trong popup
    if (fq && !hit.some((s) => foldVN(s.name) === fq)) {
      opts.push({ key: NEW_PREFIX + q.trim(), label: `➕ Tạo NCC mới "${q.trim()}"` });
    }
    return opts;
  };
  const pickSupplier = async (o: PickOpt) => {
    if (o.key.startsWith(NEW_PREFIX)) {
      const name = o.key.slice(NEW_PREFIX.length);
      try {
        const s = await createSupplier({ name });
        setPicked({ id: s.id, name: s.name });
        toast(`Đã tạo NCC "${s.name}"`, "ok");
      } catch (e: any) {
        toast(e?.message || "Lỗi tạo NCC", "err");
      }
    } else {
      setPicked({ id: Number(o.key), name: o.label });
    }
  };

  const upd = (i: number, patch: Partial<Line>) =>
    setLines((prev) => prev.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  const parsed = lines
    .map((l) => ({ sp: l.sp.trim().toUpperCase(), sl: parseFloat(l.sl.replace(",", ".")), price: parseFloat(l.price.replace(/\./g, "").replace(",", ".")) }))
    .filter((l) => l.sp && isFinite(l.sl) && l.sl > 0 && isFinite(l.price) && l.price >= 0);
  const total = parsed.reduce((s, l) => s + l.sl * l.price, 0);

  const submit = async () => {
    if (!picked) return toast("Chọn nhà cung cấp trước", "info");
    if (!parsed.length) return toast("Nhập ít nhất 1 dòng hàng (SP + SL + giá)", "info");
    if (!(await confirmDialog(`Tạo phiếu nhập ${soVN(total)}đ từ ${picked.name}?`))) return;
    setBusy(true);
    try {
      const r = await createPurchase(picked.id, parsed, note.trim());
      toast("Đã tạo phiếu nhập", "ok");
      onCreated();
      onClose();
      if (r?.purchase?.id) window.location.hash = `#/nhap-hang/${r.purchase.id}`;
    } catch (e: any) {
      toast(e?.message || "Lỗi tạo phiếu nhập", "err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div class="modal-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="modal-sheet ret-sheet" onClick={(e: any) => e.stopPropagation()}>
        <div class="modal-head"><Icon name="truck" size={16} /> Nhập hàng</div>
        {!supplierId && (
          <PickerPopup value={picked?.name || ""} placeholder="Chọn nhà cung cấp"
            onSearch={searchSuppliers} onPick={pickSupplier} />
        )}
        {supplierId && <div class="muted small">NCC: <b>{picked?.name}</b></div>}
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
            <input class="ret-price" type="text" inputMode="numeric" placeholder="Giá nhập" value={l.price}
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
        <div class="ret-total">Tổng nhập: <b>{soVN(total)}đ</b></div>
        <div class="row">
          <button class="btn" onClick={onClose}>Huỷ</button>
          <button class="btn primary" disabled={busy || !parsed.length} onClick={submit}>
            {busy ? "Đang tạo…" : "Tạo phiếu nhập"}
          </button>
        </div>
      </div>
    </div>
  );
}
