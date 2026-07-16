// Khối QUY ĐỔI ĐƠN VỊ của 1 SP (chi tiết SP #/kho/:code). 1 SP có đơn vị GỐC
// (products.unit) + nhiều đơn vị phụ với tỉ lệ: 1 <đơn vị phụ> = factor <gốc>.
// Sửa/thêm = văn phòng, xoá = admin (server gate). Data: listProductUnits/
// addProductUnit/updateProductUnit/deleteProductUnit (api.ts).
import { useEffect, useState } from "preact/hooks";
import { listProductUnits, addProductUnit, updateProductUnit, deleteProductUnit, isOffice, currentUser, soVN, type ProductUnit } from "../api";
import { Icon } from "../ui/Icon";
import { confirmDialog, toast } from "../ui/feedback";

export function ProductUnits({ code, baseUnit }: { code: string; baseUnit: string }) {
  const office = isOffice();
  const isAdmin = currentUser()?.role === "admin";
  const [units, setUnits] = useState<ProductUnit[]>([]);
  const [base, setBase] = useState(baseUnit || "cây");
  const [adding, setAdding] = useState(false);
  const [nName, setNName] = useState("");
  const [nFactor, setNFactor] = useState("");
  const [edit, setEdit] = useState<Record<number, string>>({});   // id → factor draft

  const load = () => listProductUnits(code).then((d) => { setUnits(d.units); setBase(d.base_unit); }).catch(() => {});
  useEffect(() => { load(); }, [code]);
  useEffect(() => { setBase(baseUnit || "cây"); }, [baseUnit]);   // đổi đơn vị gốc ở trên → nhãn cập nhật

  const add = async () => {
    const f = Number(nFactor.replace(",", "."));
    if (!nName.trim() || !f || f <= 0) { toast("Nhập tên đơn vị + tỉ lệ > 0", "err"); return; }
    try {
      await addProductUnit(code, nName.trim(), f);
      setNName(""); setNFactor(""); setAdding(false);
      toast("Đã thêm đơn vị", "ok"); load();
    } catch (e: any) { toast(e?.message || "Lỗi thêm đơn vị", "err"); }
  };
  const saveFactor = async (u: ProductUnit) => {
    const raw = edit[u.id];
    setEdit((d) => { const n = { ...d }; delete n[u.id]; return n; });
    if (raw === undefined) return;
    const f = Number(raw.replace(",", "."));
    if (!f || f <= 0 || f === u.factor) return;
    try { await updateProductUnit(code, u.id, u.name, f); toast("Đã lưu tỉ lệ", "ok"); load(); }
    catch (e: any) { toast(e?.message || "Lỗi lưu", "err"); }
  };
  const del = async (u: ProductUnit) => {
    if (!(await confirmDialog(`Xoá đơn vị "${u.name}" (1 ${u.name} = ${soVN(u.factor)} ${base})?`, { danger: true }))) return;
    try { await deleteProductUnit(code, u.id); toast("Đã xoá đơn vị", "ok"); load(); }
    catch (e: any) { toast(e?.message || "Lỗi xoá", "err"); }
  };

  if (!units.length && !office) return null;   // staff: không có gì thì ẩn hẳn khối

  return (
    <div class="punit-box">
      <div class="punit-head"><Icon name="refresh" size={14} /> Quy đổi đơn vị
        <span class="muted small">· gốc: {base}</span>
        {office && !adding && (
          <button class="btn small punit-add" onClick={() => setAdding(true)}><Icon name="plus" size={14} /> Thêm</button>
        )}
      </div>
      {units.map((u) => (
        <div class="punit-row" key={u.id}>
          <span class="punit-name">1 {u.name}</span>
          <span class="muted">=</span>
          {office ? (
            <input class="punit-input" inputMode="decimal"
              value={edit[u.id] !== undefined ? edit[u.id] : String(u.factor)}
              onInput={(e: any) => setEdit((d) => ({ ...d, [u.id]: e.target.value }))}
              onBlur={() => saveFactor(u)}
              onKeyDown={(e: any) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
          ) : <b>{soVN(u.factor)}</b>}
          <span class="punit-base">{base}</span>
          {isAdmin && <button class="punit-del" title="Xoá đơn vị" onClick={() => del(u)}><Icon name="close" size={14} /></button>}
        </div>
      ))}
      {!units.length && <div class="muted small">Chưa có đơn vị quy đổi — vd: 1 thùng = 30 {base}.</div>}
      {adding && (
        <div class="punit-row punit-new">
          <span class="punit-name">1 <input class="punit-input punit-name-in" placeholder="thùng" value={nName}
            onInput={(e: any) => setNName(e.target.value)} /></span>
          <span class="muted">=</span>
          <input class="punit-input" inputMode="decimal" placeholder="30" value={nFactor}
            onInput={(e: any) => setNFactor(e.target.value)}
            onKeyDown={(e: any) => { if (e.key === "Enter") add(); }} />
          <span class="punit-base">{base}</span>
          <button class="btn small primary" onClick={add}>Lưu</button>
          <button class="btn small" onClick={() => { setAdding(false); setNName(""); setNFactor(""); }}>Huỷ</button>
        </div>
      )}
    </div>
  );
}
