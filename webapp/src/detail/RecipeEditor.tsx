// Công thức (BOM) 1 SP: các nguyên liệu (product khác) + tỉ lệ (số cây NL / 1 cây
// thành phẩm). Khi nhập thùng SP này ở phiếu SX → tự trừ kho NL theo thùng người
// chọn. Định nghĩa tỉ lệ ở đây (trang chi tiết SP). Data: /api/products/{code}/recipe.
import { useEffect, useState } from "preact/hooks";
import { getRecipe, setRecipeLine, deleteRecipeLine, searchProducts, soVN, type RecipeLine } from "../api";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { toast, confirmDialog } from "../ui/feedback";
import { PickerPopup, type PickOpt } from "../ui/PickerPopup";

export function RecipeEditor({ productCode }: { productCode: string }) {
  const [lines, setLines] = useState<RecipeLine[]>([]);
  const [ing, setIng] = useState("");
  const [ratio, setRatio] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => { try { setLines(await getRecipe(productCode)); } catch { /* im */ } };
  useEffect(() => { load(); }, [productCode]);
  useEffect(() => onRealtime((e) => { if (e.type === "inventory_changed" || e.type === "resync") load(); }), [productCode]);

  const add = async () => {
    const code = ing.trim().toUpperCase();
    const r = parseFloat((ratio || "").replace(",", "."));
    if (!code) { toast("Chọn nguyên liệu", "err"); return; }
    if (!isFinite(r) || r <= 0) { toast("Tỉ lệ phải > 0", "err"); return; }
    if (code === productCode.toUpperCase()) { toast("Không tự làm nguyên liệu", "err"); return; }
    setBusy(true);
    try { await setRecipeLine(productCode, code, r); setIng(""); setRatio(""); await load(); toast("✅ Đã lưu", "ok"); }
    catch (e: any) { toast(e?.message || "Lỗi lưu", "err"); }
    finally { setBusy(false); }
  };
  const del = async (l: RecipeLine) => {
    if (!(await confirmDialog(`Bỏ nguyên liệu ${l.ingredient_code}?`, { danger: true }))) return;
    try { await deleteRecipeLine(productCode, l.id); await load(); } catch (e: any) { toast(e?.message || "Lỗi", "err"); }
  };
  const search = async (q: string): Promise<PickOpt[]> => {
    const r = await searchProducts(q).catch(() => []);
    return r.filter((s) => s.code.toUpperCase() !== productCode.toUpperCase())
      .map((s) => ({ key: s.code, label: s.code, sub: s.name || undefined }));
  };

  return (
    <section class="card">
      <label class="card-label"><Icon name="leaf" size={16} /> Công thức — nguyên liệu</label>
      <div class="muted small" style={{ marginBottom: "6px" }}>Tỉ lệ = số cây nguyên liệu cho 1 cây {productCode}. Khi nhập thùng sẽ tự trừ kho (chọn thùng nguyên liệu lúc nhập).</div>

      {lines.length === 0 ? (
        <div class="muted small">Chưa có nguyên liệu. Thêm bên dưới.</div>
      ) : (
        <div class="inv-detail-list">
          {lines.map((l) => (
            <div class="inv-detail-row" key={l.id}>
              <code class="inv-bc">{l.ingredient_code}</code>
              <span class="inv-q">× {l.ratio}</span>
              <span class="muted small">tồn {soVN(l.stock ?? 0)}</span>
              <button class="link-btn" onClick={() => del(l)} title="Bỏ"><Icon name="trash" size={15} /></button>
            </div>
          ))}
        </div>
      )}

      <div class="row" style={{ gap: "6px", marginTop: "8px" }}>
        <span style={{ flex: 1 }}>
          <PickerPopup value={ing} placeholder="Nguyên liệu" onSearch={search} onPick={(o) => setIng(o.key)} />
        </span>
        <input class="pb-amount" type="text" inputMode="decimal" style={{ width: "88px" }} placeholder="Tỉ lệ"
          value={ratio} onFocus={(e) => (e.target as HTMLInputElement).select()}
          onInput={(e: any) => setRatio(e.target.value)} />
        <button class="btn primary" disabled={busy} onClick={add}><Icon name="plus" size={16} /></button>
      </div>
    </section>
  );
}
