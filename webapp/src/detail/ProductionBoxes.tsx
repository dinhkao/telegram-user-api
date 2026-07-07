// Nhập thùng cho phiếu SX: 1 đợt = N thùng GIỐNG NHAU (cùng số cây), mã tự sinh
// (K2L-001). POST .../boxes (queueable, gửi mảng {quantity} × số thùng). onChanged()
// để phiếu tải lại tổng. Liệt kê thùng đã nhập ở phiếu này — tap → chi tiết thùng.
import { useEffect, useState } from "preact/hooks";
import { addProductionBoxes, slipBoxes, listUnits, createUnit, listPlaces, createPlace, getRecipe, searchProducts, soVN, type ProdSlip, type InvBox, type Unit, type Place, type RecipeLine } from "../api";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { SelectPopup } from "../ui/SelectPopup";
import { PickerPopup, type PickOpt } from "../ui/PickerPopup";
import { StockPickerModal } from "./StockPickerModal";

function todayLocal(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function ProductionBoxes({
  threadId,
  slip,
  onChanged,
}: {
  threadId: string;
  slip: ProdSlip;
  onChanged: () => void;
}) {
  // SP để tạo thùng — mặc định sp_name của phiếu, nhưng CHỌN được SP khác (1 phiếu
  // SX tạo thùng cho nhiều SP).
  const [prodCode, setProdCode] = useState(slip.sp_name || "");
  useEffect(() => { if (slip.sp_name && !prodCode) setProdCode(slip.sp_name); }, [slip.sp_name]);
  const hasSp = !!prodCode;
  const [amount, setAmount] = useState("");
  const [count, setCount] = useState("1");
  const [note, setNote] = useState("");
  const [mfgDate, setMfgDate] = useState(todayLocal());
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [myBoxes, setMyBoxes] = useState<InvBox[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [unitId, setUnitId] = useState<number | null>(null);   // đơn vị chứa cho đợt nhập
  useEffect(() => { listUnits().then((u) => { setUnits(u); if (u[0] && unitId == null) setUnitId(u[0].id); }).catch(() => {}); }, []);
  // Công thức nguyên liệu của SP này + thùng NL người dùng chọn để tiêu hao
  const [recipe, setRecipe] = useState<RecipeLine[]>([]);
  const [consumePicks, setConsumePicks] = useState<Record<string, { box_id: number; quantity: number }[]>>({});
  const [pickIng, setPickIng] = useState<string | null>(null);   // mã NL đang mở popup chọn thùng
  const [prodUnit, setProdUnit] = useState("cây");                 // đơn vị của SP đang nhập
  useEffect(() => {
    if (prodCode) getRecipe(prodCode).then((r) => { setRecipe(r.recipe); setProdUnit(r.unit); }).catch(() => { setRecipe([]); setProdUnit("cây"); });
    else { setRecipe([]); setProdUnit("cây"); }
  }, [prodCode]);
  const produced = (() => {
    const n = parseFloat((amount || "").replace(",", ".")), c = Math.floor(parseFloat((count || "").replace(",", ".")));
    return isFinite(n) && n > 0 && isFinite(c) && c > 0 ? n * c : 0;
  })();
  const chosenOf = (code: string) => (consumePicks[code] || []).reduce((s, p) => s + p.quantity, 0);
  // BẮT BUỘC chọn đủ thùng NL trước khi tạo thùng — CHỈ nguyên liệu bắt buộc.
  // Nguyên liệu "không bắt buộc" (optional) có thể chọn hoặc không.
  const requiredLines = recipe.filter((l) => !l.optional);
  const recipeOk = requiredLines.length === 0 || (produced > 0 && requiredLines.every((l) => chosenOf(l.ingredient_code) + 1e-6 >= l.ratio * produced));
  const createUnitPick = async (name: string) => {
    try {
      const u = await createUnit(name);
      setUnits((prev) => (prev.some((x) => x.id === u.id) ? prev : [...prev, u]));
      setUnitId(u.id);
    } catch { /* im */ }
  };
  const [places, setPlaces] = useState<Place[]>([]);
  const [placeId, setPlaceId] = useState<number | null>(null);   // vị trí kho cho thùng mới
  useEffect(() => { listPlaces().then(setPlaces).catch(() => {}); }, []);
  const createPlacePick = async (name: string) => {
    try {
      const p = await createPlace(name);
      setPlaces((prev) => (prev.some((x) => x.id === p.id) ? prev : [...prev, p]));
      setPlaceId(p.id);
    } catch { /* im */ }
  };

  const loadMine = async () => {
    try {
      setMyBoxes(await slipBoxes(threadId));
    } catch {
      /* im lặng */
    }
  };
  useEffect(() => {
    loadMine();
  }, [slip.sp_name, slip.total]);
  // Realtime: thùng đổi ở nơi khác (sửa ghi chú/số cây/vô hiệu/xuất) không luôn đổi
  // slip.total → tự tải lại list thùng của phiếu này.
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "box_changed" || e.type === "inventory_changed" || e.type === "resync") {
        clearTimeout(t); t = setTimeout(loadMine, 300);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, [threadId]);

  const submit = async () => {
    const n = parseFloat(amount.replace(",", "."));
    if (!isFinite(n) || n <= 0) {
      setMsg(`Số ${prodUnit} không hợp lệ`);
      return;
    }
    const c = Math.floor(parseFloat(count.replace(",", ".")));
    if (!isFinite(c) || c <= 0) {
      setMsg("Số thùng không hợp lệ");
      return;
    }
    if (!recipeOk) {
      setMsg("⚠ Chọn đủ thùng nguyên liệu trước khi tạo thùng");
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      const picks = Array.from({ length: c }, () => ({ quantity: n }));  // c thùng giống nhau
      const consume = Object.values(consumePicks).flat();               // thùng NL đã chọn
      const r = await addProductionBoxes(threadId, picks, note.trim(), mfgDate, unitId, consume, prodCode, placeId);
      setAmount("");
      setCount("1");
      setNote("");
      setConsumePicks({});
      if (r?._queued) {
        setMsg("⏳ Đã lưu tạm (mất mạng), sẽ gửi lại");
      } else {
        const nc = (r.consumed || []).length;
        setMsg(`✅ Đã nhập ${c} thùng${nc ? ` · trừ ${nc} phần nguyên liệu` : ""}`);
        onChanged();
        loadMine();
      }
    } catch (e: any) {
      setMsg(e?.message || "Lỗi nhập thùng");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section class="card">
      <label class="card-label"><Icon name="box" size={16} /> Nhập thùng</label>
      <div class="row">
        <label class="inline-label"><Icon name="tag" size={16} /> Sản phẩm</label>
        <PickerPopup value={prodCode} placeholder="Chọn SP" allowFreeText
          onSearch={async (q): Promise<PickOpt[]> => (await searchProducts(q).catch(() => [])).map((s) => ({ key: s.code, label: s.code, sub: s.name || undefined }))}
          onPick={(o) => setProdCode(o.key)} />
      </div>
      {!hasSp && <div class="muted small">Chọn sản phẩm trước khi nhập.</div>}

      <div class="row">
        <label class="inline-label"><Icon name="calendar" size={16} /> NSX</label>
        <input
          type="date"
          value={mfgDate}
          disabled={!hasSp}
          onInput={(e) => setMfgDate((e.target as HTMLInputElement).value)}
        />
      </div>
      <div class="row">
        <label class="inline-label"><Icon name="box" size={16} /> Đơn vị</label>
        <SelectPopup title="Đơn vị chứa" searchable onCreate={createUnitPick} disabled={!hasSp}
          value={unitId ?? ""} options={units.map((u) => ({ value: u.id, label: u.name }))}
          onChange={(v) => setUnitId(v ? Number(v) : null)} />
      </div>
      <div class="row">
        <label class="inline-label"><Icon name="box" size={16} /> Vị trí</label>
        <SelectPopup title="Vị trí kho" placeholder="— Chưa xếp —" searchable onCreate={createPlacePick} disabled={!hasSp}
          value={placeId ?? ""}
          options={[{ value: "", label: "— Chưa xếp —" }, ...places.map((p) => ({ value: p.id, label: p.name }))]}
          onChange={(v) => setPlaceId(v ? Number(v) : null)} />
      </div>
      <div class="row">
        <input
          type="text"
          inputMode="numeric"
          class="pb-count"
          value={count}
          disabled={!hasSp}
          onFocus={(e) => (e.target as HTMLInputElement).select()}
          onInput={(e) => setCount((e.target as HTMLInputElement).value)}
          placeholder="Số thùng"
          title="Số thùng giống nhau"
        />
        <span class="pb-x">thùng ×</span>
        <input
          type="text"
          inputMode="decimal"
          class="pb-amount"
          value={amount}
          disabled={!hasSp}
          onFocus={(e) => (e.target as HTMLInputElement).select()}
          onInput={(e) => setAmount((e.target as HTMLInputElement).value)}
          placeholder={`Số ${prodUnit} / thùng`}
        />
      </div>
      {recipe.length > 0 && (
        <div class="recipe-consume">
          <div class="card-label"><Icon name="leaf" size={15} /> Nguyên liệu cần trừ {produced > 0 ? `(SX ${soVN(produced)} ${prodUnit})` : ""}</div>
          {produced <= 0 && <div class="muted small">Nhập số thùng × số {prodUnit} trước để tính nguyên liệu.</div>}
          {recipe.map((l) => {
            const need = +(l.ratio * produced).toFixed(3);
            const chosen = chosenOf(l.ingredient_code);
            const enough = need > 0 && chosen >= need;
            return (
              <div class="stock-head" key={l.ingredient_code}>
                <b>{l.ingredient_code}</b>
                {l.optional && <span class="muted small">tuỳ chọn</span>}
                <span class={l.optional || enough ? "inv-pick-sum ok" : "inv-pick-sum"}>{soVN(chosen)}/{soVN(need)}</span>
                <span class="muted small">tồn {soVN(l.stock ?? 0)}</span>
                <button class="btn small" disabled={!hasSp || produced <= 0} onClick={() => setPickIng(l.ingredient_code)}>Chọn thùng</button>
              </div>
            );
          })}
        </div>
      )}

      <div class="row">
        <input
          type="text"
          value={note}
          disabled={!hasSp}
          onInput={(e) => setNote((e.target as HTMLInputElement).value)}
          placeholder="Ghi chú (tuỳ chọn)"
        />
        <button class="btn primary" disabled={!hasSp || busy || !recipeOk} onClick={submit}
          title={!recipeOk ? "Chọn đủ thùng nguyên liệu trước" : undefined}>
          {busy ? "…" : <Icon name="plus" size={16} />}
        </button>
      </div>
      {recipe.length > 0 && produced > 0 && !recipeOk && (
        <div class="muted small">⚠ Cần chọn đủ thùng nguyên liệu mới tạo được thùng.</div>
      )}
      {msg && <div class="muted small">{msg}</div>}

      {pickIng && (
        <StockPickerModal
          productCode={pickIng}
          need={+(((recipe.find((l) => l.ingredient_code === pickIng)?.ratio || 0) * produced).toFixed(3))}
          got={0}
          initial={consumePicks[pickIng] || []}
          onClose={() => setPickIng(null)}
          onPick={async (picks) => { const code = pickIng; setConsumePicks((prev) => ({ ...prev, [code]: picks })); }}
        />
      )}

      {myBoxes.length > 0 && (
        <div class="inv-summary">
          <div class="inv-total">Thùng nhập ở phiếu này ({myBoxes.length})</div>
          {/* Trực quan: mỗi thùng = 1 ô vuông, màu theo trạng thái; tap → chi tiết thùng */}
          <div class="box-grid">
            {myBoxes.map((b) => {
              const rem = b.remaining ?? b.quantity;
              const used = b.allocated ?? 0;
              const st = b.disabled ? "off" : used > 0 ? "alloc" : "in";
              const status = b.disabled ? "vô hiệu" : used > 0 ? `đã xuất ${soVN(used)}/${soVN(b.quantity)}` : "trong kho";
              return (
                <a
                  key={b.id}
                  id={`box-${b.id}`}
                  class={`box-sq ${st}`}
                  href={`#/thung/${b.id}`}
                  title={`${b.box_code} · ${soVN(rem)} ${b.product_unit || "cây"} · ${status}${b.note ? ` · ${b.note}` : ""}`}
                >
                  {b.note && <span class="bs-dot" />}
                  <span class="bs-q">{soVN(rem)}</span>
                  <span class="bs-code">{b.box_code}</span>
                </a>
              );
            })}
          </div>
          <div class="box-legend">
            <span><i class="bl in" />Trong kho</span>
            <span><i class="bl alloc" />Đã xuất</span>
            <span><i class="bl off" />Vô hiệu</span>
          </div>
        </div>
      )}
    </section>
  );
}
