// Khối QUY ĐỔI ĐƠN VỊ của 1 SP (chi tiết SP #/kho/:code). 1 SP có đơn vị GỐC
// (products.unit) + nhiều đơn vị phụ với tỉ lệ: 1 <đơn vị phụ> = factor <gốc>.
// Nút ⇄ đổi CHIỀU phương trình từng dòng ("1 thùng = 30 cây" ⇄ "1 cây = 0,033 thùng")
// cho dễ nhập tỉ lệ nhỏ. VẾ PHẢI phương trình chọn được ĐƠN VỊ THAM CHIẾU bất kỳ
// (gốc hoặc phụ khác — "1 Thùng = 3 Lốc"): chỉ là tiện NHẬP/XEM, DB luôn lưu 1 chiều
// factor theo GỐC (f = giá trị × factor tham chiếu — không có link, xoá đơn vị tham
// chiếu không ảnh hưởng gì).
// VAI ĐƠN VỊ (docs/plan-don-vi-hang-hoa.md): 3 dòng chip 📦 nguyên kiện / 👁 hiển thị
// ô thùng / 📋 kiểm kho — mỗi vai chọn tối đa 1 đơn vị (gốc hoặc phụ), tap lại = bỏ;
// lưu qua updateProduct({<vai>_unit_id}). Sửa/thêm = văn phòng, xoá = admin (server
// gate). Data: listProductUnits (kèm roles)/addProductUnit/updateProductUnit/
// deleteProductUnit + updateProduct (api.ts).
import { useEffect, useState } from "preact/hooks";
import { listProductUnits, addProductUnit, updateProductUnit, deleteProductUnit, updateProduct, isOffice, currentUser, soVN, type ProductUnit, type ProductUnitRoles } from "../api";
import { SelectPopup, type SPOption } from "../ui/SelectPopup";
import { Icon } from "../ui/Icon";
import { confirmDialog, toast } from "../ui/feedback";

const ROLE_DEFS: { key: keyof ProductUnitRoles; icon: string; label: string; hint: string }[] = [
  { key: "bulk_unit_id", icon: "📦", label: "Nguyên kiện", hint: "nhập hàng bằng đơn vị này: mỗi kiện = 1 thùng riêng, khỏi chọn đơn vị chứa" },
  { key: "display_unit_id", icon: "👁", label: "Hiển thị ô thùng", hint: "số trên ô thùng mọi nơi quy đổi sang đơn vị này (chỉ hiển thị)" },
  { key: "stocktake_unit_id", icon: "📋", label: "Kiểm kho", hint: "phiếu kiểm kho bắt đếm bằng đơn vị này + ô số lẻ đơn vị gốc" },
];
const NO_ROLES: ProductUnitRoles = { bulk_unit_id: null, display_unit_id: null, stocktake_unit_id: null };

// Hiện số gọn kiểu VN: tối đa 6 số lẻ, bỏ 0 thừa, dấu phẩy thập phân ("0,0333", "30")
const fmt = (x: number) => String(Math.round(x * 1e6) / 1e6).replace(".", ",");

export function ProductUnits({ code, baseUnit }: { code: string; baseUnit: string }) {
  const office = isOffice();
  const isAdmin = currentUser()?.role === "admin";
  const [units, setUnits] = useState<ProductUnit[]>([]);
  const [base, setBase] = useState(baseUnit || "cây");
  const [adding, setAdding] = useState(false);
  const [nName, setNName] = useState("");
  const [nFactor, setNFactor] = useState("");
  const [nFlip, setNFlip] = useState(false);                       // dòng mới đang đảo chiều?
  const [nRef, setNRef] = useState(0);                             // dòng mới: đơn vị tham chiếu (0 = gốc)
  const [edit, setEdit] = useState<Record<number, string>>({});    // id → draft số đang gõ
  const [flip, setFlip] = useState<Record<number, boolean>>({});   // id → dòng đang đảo chiều?
  const [refs, setRefs] = useState<Record<number, number>>({});    // id → đơn vị THAM CHIẾU của vế phải (0 = gốc)
  const [refPick, setRefPick] = useState<number | null>(null);     // id dòng đang mở popup chọn tham chiếu (-1 = dòng mới)
  const [roles, setRoles] = useState<ProductUnitRoles>(NO_ROLES);

  const load = () => listProductUnits(code).then((d) => { setUnits(d.units); setBase(d.base_unit); setRoles(d.roles); }).catch(() => {});
  useEffect(() => { load(); }, [code]);
  useEffect(() => { setBase(baseUnit || "cây"); }, [baseUnit]);   // đổi đơn vị gốc ở trên → nhãn cập nhật

  // Đơn vị THAM CHIẾU của vế phải phương trình: 0 = gốc, khác = 1 đơn vị phụ.
  // Chỉ là tiện nhập/xem — mọi tính toán quy về factor GỐC ngay tại chỗ.
  const refUnitOf = (rid: number) =>
    rid === 0 ? { id: 0, name: base, factor: 1 } : (units.find((x) => x.id === rid) || { id: 0, name: base, factor: 1 });
  const refOptions = (excludeId?: number): SPOption[] => [
    { value: 0, label: `${base} (gốc)` },
    ...units.filter((x) => x.id !== excludeId)
      .map((x) => ({ value: x.id, label: x.name, sub: `1 ${x.name} = ${fmt(x.factor)} ${base}` })),
  ];

  const add = async () => {
    const raw = Number(nFactor.replace(",", "."));
    if (!nName.trim() || !raw || raw <= 0) { toast("Nhập tên đơn vị + tỉ lệ > 0", "err"); return; }
    const R = refUnitOf(nRef);
    // đảo chiều: người dùng nhập "1 <tham chiếu> = raw <đơn-vị-mới>"; quy về gốc qua factor tham chiếu
    const f = nFlip ? R.factor / raw : raw * R.factor;
    try {
      await addProductUnit(code, nName.trim(), f);
      setNName(""); setNFactor(""); setNFlip(false); setNRef(0); setAdding(false);
      toast("Đã thêm đơn vị", "ok"); load();
    } catch (e: any) { toast(e?.message || "Lỗi thêm đơn vị", "err"); }
  };
  const heldRoles = (unitId: number) =>
    ROLE_DEFS.filter((rd) => roles[rd.key] === unitId).map((rd) => rd.label);
  const saveFactor = async (u: ProductUnit) => {
    const raw = edit[u.id];
    setEdit((d) => { const n = { ...d }; delete n[u.id]; return n; });
    if (raw === undefined) return;
    const v = Number(raw.replace(",", "."));
    if (!v || v <= 0) return;
    const R = refUnitOf(refs[u.id] ?? 0);
    const f = flip[u.id] ? R.factor / v : v * R.factor;   // quy về factor GỐC
    if (Math.abs(f - u.factor) < 1e-9) return;
    // Đơn vị đang giữ vai: đổi tỉ lệ đổi luôn cách đọc số kiện/hiển thị của thùng cũ
    const held = heldRoles(u.id);
    if (held.length && !(await confirmDialog(
      `"${u.name}" đang là đơn vị ${held.join(" + ")}. Đổi tỉ lệ sẽ đổi cách quy đổi ở các chỗ đó (số gốc trong kho không đổi). Lưu?`))) { return; }
    try { await updateProductUnit(code, u.id, u.name, f); toast("Đã lưu tỉ lệ", "ok"); load(); }
    catch (e: any) { toast(e?.message || "Lỗi lưu", "err"); }
  };
  // VAI đơn vị: tap chip = chọn, tap lại = bỏ. value: 0 = đơn vị gốc, >0 = đơn vị phụ.
  const setRole = async (key: keyof ProductUnitRoles, value: number | null) => {
    const prev = roles;
    setRoles((r) => ({ ...r, [key]: value }));   // optimistic — lỗi thì revert
    try { await updateProduct(code, { [key]: value }); }
    catch (e: any) { setRoles(prev); toast(e?.message || "Lỗi lưu vai đơn vị", "err"); }
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

  const anyRoleSet = ROLE_DEFS.some((rd) => roles[rd.key] !== null);
  if (!units.length && !office && !anyRoleSet) return null;   // staff: không có gì thì ẩn hẳn khối

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
        const R = refUnitOf(refs[u.id] ?? 0);
        const ratio = u.factor / R.factor;   // 1 u = ratio R (R = gốc thì ratio = factor)
        const shown = edit[u.id] !== undefined ? edit[u.id] : fmt(inv ? 1 / ratio : ratio);
        // vế THAM CHIẾU: office + có ≥2 lựa chọn → bấm được để đổi ("1 Thùng = 3 Lốc")
        const refBtn = office && units.length > 1
          ? <button class="punit-refbtn" title="Đổi đơn vị tham chiếu" onClick={() => setRefPick(u.id)}>{R.name}</button>
          : <span class="punit-base">{R.name}</span>;
        return (
          <div class="punit-row" key={u.id}>
            <span class="punit-name">1 {inv ? refBtn : u.name}</span>
            <span class="punit-eq">=</span>
            {office ? (
              <input class="punit-input" inputMode="decimal"
                value={shown}
                onInput={(e: any) => setEdit((d) => ({ ...d, [u.id]: e.target.value }))}
                onBlur={() => saveFactor(u)}
                onKeyDown={(e: any) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
            ) : <b>{soVN(Math.round((inv ? 1 / ratio : ratio) * 1e6) / 1e6)}</b>}
            {inv ? <span class="punit-base">{u.name}</span> : refBtn}
            <button class="punit-flip" title="Đổi chiều quy đổi" onClick={() => toggleFlip(u.id)}>⇄</button>
            {isAdmin && <button class="punit-del" title="Xoá đơn vị" onClick={() => del(u)}><Icon name="close" size={14} /></button>}
          </div>
        );
      })}
      {/* Popup chọn đơn vị tham chiếu (dòng đang sửa hoặc dòng mới = -1) */}
      <SelectPopup open={refPick !== null} onClose={() => setRefPick(null)} title="Quy đổi theo đơn vị nào?"
        value={refPick === -1 ? nRef : (refPick != null ? (refs[refPick] ?? 0) : 0)}
        options={refOptions(refPick != null && refPick > 0 ? refPick : undefined)}
        onChange={(v) => {
          const rid = Number(v) || 0;
          if (refPick === -1) { setNRef(rid); setNFactor(""); }
          else if (refPick != null) {
            setEdit((d) => { const n = { ...d }; delete n[refPick]; return n; });   // ô hiện lại số theo hệ mới
            setRefs((m) => ({ ...m, [refPick]: rid }));
          }
          setRefPick(null);
        }} />
      {!units.length && <div class="punit-empty">Chưa có đơn vị quy đổi — vd: 1 thùng = 30 {base}.</div>}
      {(() => {
        // VAI ĐƠN VỊ — office sửa được; staff chỉ thấy vai đã gán
        const opts = [{ id: 0, name: `${base} (gốc)` }, ...units.map((u) => ({ id: u.id, name: u.name }))];
        const anySet = ROLE_DEFS.some((rd) => roles[rd.key] !== null);
        if (!office && !anySet) return null;
        const nameOf = (v: number | null) => v === null ? null : (opts.find((o) => o.id === v)?.name || "?");
        return (
          <div class="punit-roles">
            {ROLE_DEFS.map((rd) => (
              (office || roles[rd.key] !== null) && (
                <div class="punit-role-row" key={rd.key}>
                  <span class="punit-role-label" title={rd.hint}>{rd.icon} {rd.label}</span>
                  {office ? opts.map((o) => {
                    const on = roles[rd.key] === o.id;
                    return (
                      <button key={o.id} class={"punit-role-chip" + (on ? " on" : "")}
                        title={rd.hint} onClick={() => setRole(rd.key, on ? null : o.id)}>{o.name}</button>
                    );
                  }) : <b>{nameOf(roles[rd.key])}</b>}
                </div>
              )
            ))}
            <div class="punit-role-hint">Nguyên kiện: nhập hàng khỏi chọn đơn vị chứa · Hiển thị: số trên ô thùng · Kiểm kho: đơn vị bắt buộc khi đếm</div>
          </div>
        );
      })()}
      {adding && (() => {
        const R = refUnitOf(nRef);
        // vế tham chiếu của dòng mới: bấm đổi được khi có đơn vị phụ khác để chọn
        const nRefBtn = units.length > 0
          ? <button class="punit-refbtn" title="Đổi đơn vị tham chiếu" onClick={() => setRefPick(-1)}>{R.name}</button>
          : <span class="punit-base">{R.name}</span>;
        return (
          <>
            <div class="punit-row punit-new">
              {nFlip ? (
                <>
                  <span class="punit-name">1 {nRefBtn}</span>
                  <span class="punit-eq">=</span>
                  <input class="punit-input" inputMode="decimal" placeholder="0,5" value={nFactor}
                    onInput={(e: any) => setNFactor(e.target.value)}
                    onKeyDown={(e: any) => { if (e.key === "Enter") add(); }} />
                  <input class="punit-input punit-name-in" placeholder="kg" value={nName}
                    onInput={(e: any) => setNName(e.target.value)} />
                </>
              ) : (
                <>
                  <span class="punit-name">1</span>
                  <input class="punit-input punit-name-in" placeholder="thùng" value={nName}
                    onInput={(e: any) => setNName(e.target.value)} />
                  <span class="punit-eq">=</span>
                  <input class="punit-input" inputMode="decimal" placeholder="30" value={nFactor}
                    onInput={(e: any) => setNFactor(e.target.value)}
                    onKeyDown={(e: any) => { if (e.key === "Enter") add(); }} />
                  {nRefBtn}
                </>
              )}
              <button class="punit-flip" title="Đổi chiều quy đổi" onClick={() => { setNFlip(!nFlip); setNFactor(""); }}>⇄</button>
            </div>
            {/* Preview chiều CHUẨN sẽ lưu (luôn quy về GỐC) — nhập theo đơn vị khác vẫn thấy hệ quy ra sao */}
            {(() => {
              const v = Number(nFactor.replace(",", "."));
              if (!nName.trim() || !v || v <= 0) return null;
              const f = nFlip ? R.factor / v : v * R.factor;
              return <div class="muted small" style={{ margin: "0 0 4px 2px" }}>→ sẽ lưu: 1 {nName.trim()} = {fmt(f)} {base}</div>;
            })()}
            <div class="punit-new-actions">
              <button class="btn small" onClick={() => { setAdding(false); setNName(""); setNFactor(""); setNFlip(false); setNRef(0); }}>Huỷ</button>
              <button class="btn small primary" onClick={add}><Icon name="check" size={14} /> Lưu đơn vị</button>
            </div>
          </>
        );
      })()}
    </div>
  );
}
