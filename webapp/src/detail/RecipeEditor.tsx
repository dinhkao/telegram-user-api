// Công thức (BOM) 1 SP: NL CHÍNH (tỉ lệ = lượng NL / 1 cây thành phẩm — chỉ phiếu
// ĐÓNG GÓI bắt buộc trừ) + NGUYÊN LIỆU PHỤ (bao bì/tem… — trừ kho ở CẢ phiếu sản
// xuất LẪN đóng gói khi bật "Yêu cầu NL phụ", toggle ngay ở đây, lưu
// products.aux_required). Data: /api/products/{code}/recipe + updateProduct.
import { useEffect, useState } from "preact/hooks";
import { getRecipe, setRecipeLine, deleteRecipeLine, updateProduct, searchProducts, soVN, type RecipeLine } from "../api";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { toast, confirmDialog } from "../ui/feedback";
import { PickerPopup, type PickOpt } from "../ui/PickerPopup";

// 1 khu nguyên liệu (chính / phụ): danh sách + dòng thêm. aux quyết định loại.
function IngSection({ productCode, lines, aux, onChanged }: {
  productCode: string; lines: RecipeLine[]; aux: boolean; onChanged: () => void;
}) {
  const [ing, setIng] = useState("");
  const [ratio, setRatio] = useState("");
  const [busy, setBusy] = useState(false);

  const add = async () => {
    const code = ing.trim().toUpperCase();
    const r = parseFloat((ratio || "").replace(",", "."));
    if (!code) { toast("Chọn nguyên liệu", "err"); return; }
    if (!isFinite(r) || r <= 0) { toast("Tỉ lệ phải > 0", "err"); return; }
    if (code === productCode.toUpperCase()) { toast("Không tự làm nguyên liệu", "err"); return; }
    setBusy(true);
    try { await setRecipeLine(productCode, code, r, aux); setIng(""); setRatio(""); onChanged(); toast("✅ Đã lưu", "ok"); }
    catch (e: any) { toast(e?.message || "Lỗi lưu", "err"); }
    finally { setBusy(false); }
  };
  const del = async (l: RecipeLine) => {
    if (!(await confirmDialog(`Bỏ nguyên liệu ${l.ingredient_code}?`, { danger: true }))) return;
    try { await deleteRecipeLine(productCode, l.id); onChanged(); } catch (e: any) { toast(e?.message || "Lỗi", "err"); }
  };
  const search = async (q: string): Promise<PickOpt[]> => {
    const r = await searchProducts(q).catch(() => []);
    return r.filter((s) => s.code.toUpperCase() !== productCode.toUpperCase())
      .map((s) => ({ key: s.code, label: s.code, sub: s.name || undefined }));
  };

  return (
    <>
      {lines.length === 0 ? (
        <div class="muted small">{aux ? "Chưa có nguyên liệu phụ." : "Chưa có nguyên liệu. Thêm bên dưới."}</div>
      ) : (
        <div class="inv-detail-list">
          {lines.map((l) => (
            <div class="inv-detail-row" key={l.id}>
              <code class="inv-bc">{l.ingredient_code}</code>
              <span class="inv-q">× {l.ratio}</span>
              <span class="muted small">tồn {soVN(l.stock ?? 0)} {l.unit || ""}</span>
              <button class="link-btn" onClick={() => del(l)} title="Bỏ"><Icon name="trash" size={15} /></button>
            </div>
          ))}
        </div>
      )}
      <div class="row" style={{ gap: "6px", marginTop: "8px" }}>
        <span style={{ flex: 1 }}>
          <PickerPopup value={ing} placeholder={aux ? "Nguyên liệu phụ" : "Nguyên liệu"} onSearch={search} onPick={(o) => setIng(o.key)} />
        </span>
        <input class="pb-amount" type="text" inputMode="decimal" style={{ width: "72px" }} placeholder="Tỉ lệ"
          value={ratio} onFocus={(e) => (e.target as HTMLInputElement).select()}
          onInput={(e: any) => setRatio(e.target.value)} />
        <button class="btn primary" disabled={busy} onClick={add}><Icon name="plus" size={16} /></button>
      </div>
    </>
  );
}

export function RecipeEditor({ productCode }: { productCode: string }) {
  const [lines, setLines] = useState<RecipeLine[]>([]);
  const [unit, setUnit] = useState("cây");
  const [auxRequired, setAuxRequired] = useState(true);
  const [togBusy, setTogBusy] = useState(false);

  const load = async () => {
    try { const r = await getRecipe(productCode); setLines(r.recipe); setUnit(r.unit); setAuxRequired(r.aux_required); }
    catch { /* im */ }
  };
  useEffect(() => { load(); }, [productCode]);
  useEffect(() => onRealtime((e) => { if (e.type === "inventory_changed" || e.type === "resync") load(); }), [productCode]);

  const main = lines.filter((l) => !l.aux);
  const auxLines = lines.filter((l) => !!l.aux);

  const toggleAux = async () => {
    setTogBusy(true);
    try {
      await updateProduct(productCode, { aux_required: !auxRequired });
      setAuxRequired(!auxRequired);
      toast(!auxRequired ? "Đã BẬT yêu cầu NL phụ khi sản xuất" : "Đã TẮT yêu cầu NL phụ — sản xuất không cần trừ NL phụ", "ok");
    } catch (e: any) {
      toast(e?.message || "Lỗi lưu", "err");
    } finally {
      setTogBusy(false);
    }
  };

  return (
    <section class="card">
      <label class="card-label"><Icon name="leaf" size={16} /> Công thức — nguyên liệu</label>
      <div class="muted small" style={{ marginBottom: "6px" }}>Tỉ lệ = lượng nguyên liệu cho 1 {unit} {productCode}. Chỉ phiếu ĐÓNG GÓI mới bắt buộc trừ nguyên liệu chính; phiếu sản xuất không cần.</div>
      <IngSection productCode={productCode} lines={main} aux={false} onChanged={load} />

      <div class="recipe-aux-head">
        <label class="card-label" style={{ margin: 0 }}><Icon name="tag" size={15} /> Nguyên liệu phụ</label>
        <button class={"chip" + (auxRequired ? " active" : "")} disabled={togBusy} onClick={toggleAux}
          title="Bật: nhập thùng từ phiếu SX (cả sản xuất lẫn đóng gói) phải chọn đủ thùng NL phụ để trừ kho">
          {auxRequired ? "✓ Yêu cầu khi sản xuất" : "Không yêu cầu"}
        </button>
      </div>
      <div class="muted small" style={{ marginBottom: "6px" }}>
        Bao bì/tem/hộp… {auxRequired
          ? "Đang BẬT — nhập thùng ở MỌI phiếu (sản xuất + đóng gói) phải chọn thùng NL phụ để trừ kho."
          : "Đang TẮT — sản xuất không bắt trừ NL phụ (danh sách giữ nguyên, bật lại là áp dụng)."}
      </div>
      <IngSection productCode={productCode} lines={auxLines} aux={true} onChanged={load} />
    </section>
  );
}
