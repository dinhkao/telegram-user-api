// Khối QUY ĐỔI ĐƠN VỊ của 1 SP (chi tiết SP #/kho/:code). 1 SP có đơn vị GỐC
// (products.unit) + nhiều đơn vị phụ với tỉ lệ: 1 <đơn vị phụ> = factor <gốc>.
// Nút ⇄ đổi CHIỀU phương trình từng dòng ("1 thùng = 30 cây" ⇄ "1 cây = 0,033 thùng")
// cho dễ nhập tỉ lệ nhỏ — DB luôn lưu 1 chiều (factor = số gốc / 1 đơn vị phụ).
// Sửa/thêm = văn phòng, xoá = admin (server gate). Data: listProductUnits/
// addProductUnit/updateProductUnit/deleteProductUnit (api.ts).
import { useEffect, useState } from "preact/hooks";
import { listProductUnits, addProductUnit, updateProductUnit, deleteProductUnit, isOffice, currentUser, soVN, type ProductUnit } from "../api";
import { Icon } from "../ui/Icon";
import { confirmDialog, toast } from "../ui/feedback";

// Hiện số gọn: tối đa 6 số lẻ, bỏ 0 thừa ("0.033333", "30")
const fmt = (x: number) => String(Math.round(x * 1e6) / 1e6);

export function ProductUnits({ code, baseUnit }: { code: string; baseUnit: string }) {
  const office = isOffice();
  const isAdmin = currentUser()?.role === "admin";
  const [units, setUnits] = useState<ProductUnit[]>([]);
  const [base, setBase] = useState(baseUnit || "cây");
  const [adding, setAdding] = useState(false);
  const [nName, setNName] = useState("");
  const [nFactor, setNFactor] = useState("");
  const [nFlip, setNFlip] = useState(false);                       // dòng mới đang đảo chiều?
  const [edit, setEdit] = useState<Record<number, string>>({});    // id → draft số đang gõ
  const [flip, setFlip] = useState<Record<number, boolean>>({});   // id → dòng đang đảo chiều?

  const load = () => listProductUnits(code).then((d) => { setUnits(d.units); setBase(d.base_unit); }).catch(() => {});
  useEffect(() => { load(); }, [code]);
  useEffect(() => { setBase(baseUnit || "cây"); }, [baseUnit]);   // đổi đơn vị gốc ở trên → nhãn cập nhật

  const add = async () => {
    const raw = Number(nFactor.replace(",", "."));
    if (!nName.trim() || !raw || raw <= 0) { toast("Nhập tên đơn vị + tỉ lệ > 0", "err"); return; }
    const f = nFlip ? 1 / raw : raw;   // đảo chiều: người dùng nhập "1 gốc = raw đơn-vị-mới"
    try {
      await addProductUnit(code, nName.trim(), f);
      setNName(""); setNFactor(""); setNFlip(false); setAdding(false);
      toast("Đã thêm đơn vị", "ok"); load();
    } catch (e: any) { toast(e?.message || "Lỗi thêm đơn vị", "err"); }
  };
  const saveFactor = async (u: ProductUnit) => {
    const raw = edit[u.id];
    setEdit((d) => { const n = { ...d }; delete n[u.id]; return n; });
    if (raw === undefined) return;
    const v = Number(raw.replace(",", "."));
    if (!v || v <= 0) return;
    const f = flip[u.id] ? 1 / v : v;
    if (Math.abs(f - u.factor) < 1e-9) return;
    try { await updateProductUnit(code, u.id, u.name, f); toast("Đã lưu tỉ lệ", "ok"); load(); }
    catch (e: any) { toast(e?.message || "Lỗi lưu", "err"); }
  };
  const del = async (u: ProductUnit) => {
    if (!(await confirmDialog(`Xoá đơn vị "${u.name}" (1 ${u.name} = ${soVN(u.factor)} ${base})?`, { danger: true }))) return;
    try { await deleteProductUnit(code, u.id); toast("Đã xoá đơn vị", "ok"); load(); }
    catch (e: any) { toast(e?.message || "Lỗi xoá", "err"); }
  };
  // Đảo chiều 1 dòng: xoá draft đang gõ để ô hiện lại số đã lưu theo chiều mới
  const toggleFlip = (id: number) => {
    setEdit((d) => { const n = { ...d }; delete n[id]; return n; });
    setFlip((m) => ({ ...m, [id]: !m[id] }));
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
      {units.map((u) => {
        const inv = !!flip[u.id];
        const shown = edit[u.id] !== undefined ? edit[u.id] : fmt(inv ? 1 / u.factor : u.factor);
        return (
          <div class="punit-row" key={u.id}>
            <span class="punit-name">1 {inv ? base : u.name}</span>
            <span class="muted">=</span>
            {office ? (
              <input class="punit-input" inputMode="decimal"
                value={shown}
                onInput={(e: any) => setEdit((d) => ({ ...d, [u.id]: e.target.value }))}
                onBlur={() => saveFactor(u)}
                onKeyDown={(e: any) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
            ) : <b>{soVN(inv ? Math.round(1 / u.factor * 1e6) / 1e6 : u.factor)}</b>}
            <span class="punit-base">{inv ? u.name : base}</span>
            <button class="punit-flip" title="Đổi chiều quy đổi" onClick={() => toggleFlip(u.id)}>⇄</button>
            {isAdmin && <button class="punit-del" title="Xoá đơn vị" onClick={() => del(u)}><Icon name="close" size={14} /></button>}
          </div>
        );
      })}
      {!units.length && <div class="muted small">Chưa có đơn vị quy đổi — vd: 1 thùng = 30 {base}.</div>}
      {adding && (
        <>
          <div class="punit-row punit-new">
            {nFlip ? (
              <>
                <span class="punit-name">1 {base}</span>
                <span class="muted">=</span>
                <input class="punit-input" inputMode="decimal" placeholder="0,5" value={nFactor}
                  onInput={(e: any) => setNFactor(e.target.value)}
                  onKeyDown={(e: any) => { if (e.key === "Enter") add(); }} />
                <input class="punit-input punit-name-in" placeholder="kg" value={nName}
                  onInput={(e: any) => setNName(e.target.value)} />
              </>
            ) : (
              <>
                <span class="punit-name">1 <input class="punit-input punit-name-in" placeholder="thùng" value={nName}
                  onInput={(e: any) => setNName(e.target.value)} /></span>
                <span class="muted">=</span>
                <input class="punit-input" inputMode="decimal" placeholder="30" value={nFactor}
                  onInput={(e: any) => setNFactor(e.target.value)}
                  onKeyDown={(e: any) => { if (e.key === "Enter") add(); }} />
                <span class="punit-base">{base}</span>
              </>
            )}
            <button class="punit-flip" title="Đổi chiều quy đổi" onClick={() => { setNFlip(!nFlip); setNFactor(""); }}>⇄</button>
            <button class="btn small primary" onClick={add}>Lưu</button>
            <button class="btn small" onClick={() => { setAdding(false); setNName(""); setNFactor(""); setNFlip(false); }}>Huỷ</button>
          </div>
          {/* Preview chiều CHUẨN sẽ lưu — nhập đảo chiều vẫn thấy hệ quy ra sao */}
          {(() => {
            const v = Number(nFactor.replace(",", "."));
            if (!nName.trim() || !v || v <= 0) return null;
            const f = nFlip ? 1 / v : v;
            return <div class="muted small" style={{ margin: "-2px 0 4px 2px" }}>= 1 {nName.trim()} = {fmt(f)} {base}</div>;
          })()}
        </>
      )}
    </div>
  );
}
