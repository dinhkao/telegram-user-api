// Trang SỬA phiếu nhập hàng (#/nhap-hang/:id/sua) — tách khỏi trang chi tiết,
// tương tự trang sửa hoá đơn của đơn. Lưu xong quay về chi tiết phiếu.
import { useEffect, useState } from "preact/hooks";
import { PageHead } from "../ui/PageHead";
import {
  createProduct, getPurchase, searchProducts, soVN,
  updatePurchase, type PurchaseSlip,
} from "../api";
import { buildPurchaseProductOptions, isCreateProd, codeFromCreateKey, unitChoicesFor, type UnitChoice } from "../detail/purchaseProduct";
import { PurchaseUnitPicker } from "../detail/PurchaseUnitPicker";
import { PickerPopup } from "../ui/PickerPopup";
import { parseMoney, parseQty } from "../format";
import { toast } from "../ui/feedback";
import { ErrorState, Loading } from "../ui/states";
import { Icon } from "../ui/Icon";

type Line = { sp: string; sl: string; price: string; unit?: string; factor?: number };

export function PurchaseEdit({ id }: { id: string }) {
  const [purchase, setPurchase] = useState<PurchaseSlip | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [lines, setLines] = useState<Line[]>([]);
  const [note, setNote] = useState("");
  // Sửa phiếu nhập mở cho MỌI người dùng đăng nhập (2026-07-17) — chỉ khoá theo
  // trạng thái phiếu (đã xoá / đã chốt nhập kho).

  // đơn vị nhập theo mã SP: gốc + quy đổi (product_units) — nạp khi chọn/tải SP
  const [unitsBySp, setUnitsBySp] = useState<Record<string, UnitChoice[]>>({});
  const loadUnits = (sp: string) => {
    const key = sp.trim().toUpperCase();
    if (!key) return;
    setUnitsBySp((m) => { if (m[key]) return m; unitChoicesFor(key).then((cs) => setUnitsBySp((n) => ({ ...n, [key]: cs }))); return m; });
  };

  const load = async () => {
    try {
      const r = await getPurchase(id);
      setPurchase(r);
      setLines((r.items || []).map((x) => ({ sp: x.sp, sl: String(x.sl), price: String(x.price),
        ...(x.unit && (x.unit_factor || 0) > 0 ? { unit: x.unit, factor: x.unit_factor } : {}) })));
      (r.items || []).forEach((x) => loadUnits(x.sp));
      setNote(r.note || "");
      setErr("");
    } catch (e: any) {
      setErr(e?.message || "Lỗi tải phiếu");
    }
  };

  useEffect(() => { load(); }, [id]);

  const updateLine = (i: number, patch: Partial<Line>) =>
    setLines((prev) => prev.map((line, j) => (j === i ? { ...line, ...patch } : line)));

  const parsed = lines
    .map((line) => ({
      sp: line.sp.trim().toUpperCase(),
      sl: parseQty(line.sl),
      price: parseMoney(line.price),
      // đơn vị nhập khác gốc → snapshot vào item (SL + giá tính theo đơn vị đó)
      ...(line.unit && (line.factor || 0) > 0 && line.factor !== 1 ? { unit: line.unit, unit_factor: line.factor } : {}),
    }))
    .filter((line) => line.sp && isFinite(line.sl) && line.sl > 0 && isFinite(line.price) && line.price >= 0);
  const total = parsed.reduce((sum, line) => sum + line.sl * line.price, 0);
  const deleted = !!purchase?.deleted_at;
  const goodsHandled = !!purchase?.goods_handled_at;   // đã nhập kho → khoá sửa (server cũng chặn)

  const save = async () => {
    if (deleted) return toast("Phiếu đã bị xoá, không thể sửa", "info");
    if (goodsHandled) return toast("Phiếu đã nhập kho — không sửa hàng được nữa", "info");
    if (!parsed.length) return toast("Cần ít nhất 1 dòng hàng hợp lệ", "info");
    setBusy(true);
    try {
      await updatePurchase(Number(id), parsed, note.trim());
      toast("Đã lưu phiếu nhập", "ok");
      window.location.hash = `#/nhap-hang/${id}`;
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu phiếu", "err");
    } finally {
      setBusy(false);
    }
  };

  if (err) return <ErrorState msg={err} onRetry={load} />;
  if (!purchase) return <Loading />;

  return (
    <div class="pur-edit-page">
      <PageHead fallback={`#/nhap-hang/${id}`}
        title={<><Icon name="edit" size={18} /> Sửa phiếu nhập</>}
        sub={<>{purchase.supplier_name || `NCC #${purchase.supplier_id}`} · Phiếu #{purchase.id}</>} />

      {deleted && (
        <div class="card co-adv-locked muted small">
          <Icon name="lock" size={14} /> Phiếu đã bị xoá{purchase.deleted_by ? ` bởi ${purchase.deleted_by}` : ""} — không thể sửa.
        </div>
      )}
      {goodsHandled && !deleted && (
        <div class="card co-adv-locked muted small">
          <Icon name="lock" size={14} /> Phiếu đã nhập kho — hàng đã vào thùng, không sửa được nữa.
        </div>
      )}

      {!deleted && !goodsHandled && (
        <section class="card pur-edit-card">
          <div class="card-label"><Icon name="box" size={15} /> Hàng nhập</div>
          <div class="ret-sheet">
            {lines.map((line, i) => (
              <div class="ret-line" key={i}>
                <div class="ret-sp">
                  <PickerPopup
                    value={line.sp}
                    placeholder="Mã SP"
                    onSearch={async (q) => buildPurchaseProductOptions(await searchProducts(q).catch(() => []), q)}
                    onPick={async (o) => {
                      if (isCreateProd(o.key)) {
                        const code = codeFromCreateKey(o.key);
                        try { await createProduct(code); updateLine(i, { sp: code, unit: undefined, factor: undefined }); loadUnits(code); toast(`Đã tạo mã hàng "${code}"`, "ok"); }
                        catch (e: any) { toast(e?.message || "Lỗi tạo mã hàng", "err"); }
                      } else { updateLine(i, { sp: o.key, unit: undefined, factor: undefined }); loadUnits(o.key); }
                    }}
                  />
                </div>
                <input
                  class="ret-sl"
                  type="text"
                  inputMode="decimal"
                  value={line.sl}
                  aria-label={`Số lượng dòng ${i + 1}`}
                  onFocus={(e) => (e.target as HTMLInputElement).select()}
                  onInput={(e) => updateLine(i, { sl: (e.target as HTMLInputElement).value })}
                />
                <input
                  class="ret-price"
                  type="text"
                  inputMode="numeric"
                  value={line.price}
                  aria-label={`Đơn giá dòng ${i + 1}`}
                  onFocus={(e) => (e.target as HTMLInputElement).select()}
                  onInput={(e) => updateLine(i, { price: (e.target as HTMLInputElement).value })}
                />
                {lines.length > 1 && (
                  <button class="btn small" onClick={() => setLines((prev) => prev.filter((_, j) => j !== i))}>
                    <Icon name="close" size={14} />
                  </button>
                )}
                <PurchaseUnitPicker code={line.sp} line={line} choices={unitsBySp[line.sp.trim().toUpperCase()]}
                  onChoices={(k, list) => setUnitsBySp((m) => ({ ...m, [k]: list }))}
                  onPick={(u) => updateLine(i, u.factor === 1 ? { unit: undefined, factor: undefined } : { unit: u.name, factor: u.factor })} />
              </div>
            ))}
            <button class="btn small" onClick={() => setLines((prev) => [...prev, { sp: "", sl: "1", price: "" }])}>
              <Icon name="plus" size={14} /> Thêm dòng
            </button>
            <input
              type="text"
              placeholder="Ghi chú"
              value={note}
              onInput={(e) => setNote((e.target as HTMLInputElement).value)}
            />
            <div class="ret-total">Tổng nhập: <b>{soVN(total)}đ</b></div>
            <div class="row pur-edit-actions">
              <a class="btn" href={`#/nhap-hang/${id}`}>Huỷ</a>
              <button class="btn primary" disabled={busy || !parsed.length} onClick={save}>
                {busy ? "Đang lưu…" : "Lưu phiếu"}
              </button>
            </div>
          </div>
        </section>
      )}

    </div>
  );
}
