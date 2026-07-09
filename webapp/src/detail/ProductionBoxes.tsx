// Nhập thùng cho phiếu SX: 1 đợt = N thùng GIỐNG NHAU (cùng số cây), mã tự sinh
// (K2L-001). POST .../boxes (queueable, gửi mảng {quantity} × số thùng). onChanged()
// để phiếu tải lại tổng. Liệt kê thùng đã nhập ở phiếu này — tap → chi tiết thùng.
import { useEffect, useRef, useState } from "preact/hooks";
import { addProductionBoxes, slipBoxes, listUnits, createUnit, listPlaces, createPlace, getRecipe, searchProducts, soVN, type ProdSlip, type InvBox, type Unit, type Place, type RecipeLine } from "../api";
import { onRealtime } from "../realtime";
import { usePopupBack } from "../ui/usePopupBack";
import { confirmDialog, toast } from "../ui/feedback";
import { CameraBox, cameraSupported, uploadProcessed, type Processed } from "./CameraBox";
import { Icon } from "../ui/Icon";
import { SelectPopup } from "../ui/SelectPopup";
import { PickerPopup, type PickOpt } from "../ui/PickerPopup";
import { StockPickerModal } from "./StockPickerModal";
import { BoxLabelGrid } from "./BoxLabelGrid";

function todayLocal(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

// NHÁP form nhập thùng theo PHIẾU (module scope): thoát trang quay lại vẫn nhập tiếp
// (kể cả thùng NL đã chọn). Nháp = gương của state nên nhập xong đợt nào form reset
// gì nháp theo nấy; sống trong phiên app, reload thì mất.
type BoxDraft = {
  prodCode: string; amount: string; count: string; note: string; mfgDate: string;
  unitId: number | null; placeId: number | null;
  consumePicks: Record<string, { box_id: number; quantity: number }[]>;
};
const boxDrafts = new Map<string, BoxDraft>();

export function ProductionBoxes({
  threadId,
  slip,
  onChanged,
  locked,
}: {
  threadId: string;
  slip: ProdSlip;
  onChanged: () => void;
  locked?: boolean;
}) {
  // SP để tạo thùng — mặc định sp_name của phiếu, nhưng CHỌN được SP khác (1 phiếu
  // SX tạo thùng cho nhiều SP). Có nháp cũ (thoát ra vào lại) → khôi phục từ nháp.
  const draft = boxDrafts.get(threadId);
  const [prodCode, setProdCode] = useState(draft?.prodCode || slip.sp_name || "");
  useEffect(() => { if (slip.sp_name && !prodCode) setProdCode(slip.sp_name); }, [slip.sp_name]);
  const hasSp = !!prodCode;
  const [amount, setAmount] = useState(draft?.amount || "");
  const [count, setCount] = useState(draft?.count || "1");
  const [note, setNote] = useState(draft?.note || "");
  const [mfgDate, setMfgDate] = useState(draft?.mfgDate || todayLocal());
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [myBoxes, setMyBoxes] = useState<InvBox[]>([]);
  // Ảnh BẮT BUỘC: bấm "Nhập" mở camera ở chế độ COLLECT (chụp trước — buffer), ĐÓNG
  // camera có ≥1 ảnh mới TẠO thùng rồi upload ảnh vào PHIẾU + mọi thùng; 0 ảnh → không
  // tạo gì. Xong → popup nhắc GHI MÃ lên thùng (liệt kê ô thùng mới).
  const [camBases, setCamBases] = useState<string[] | null>(null);
  const capturedRef = useRef<Processed[]>([]);           // ảnh đã chụp/chọn chờ upload
  const [pendingCreate, setPendingCreate] = useState<null | {
    picks: { quantity: number }[]; note: string; mfgDate: string; unitId: number | null;
    consume: { box_id: number; quantity: number }[]; prodCode: string; placeId: number | null; count: number;
  }>(null);
  const [codeBoxes, setCodeBoxes] = useState<InvBox[] | null>(null);
  usePopupBack(!!codeBoxes, () => setCodeBoxes(null));
  const [mineView, setMineView] = useState<"grid" | "list">("grid");
  const [units, setUnits] = useState<Unit[]>([]);
  const [unitId, setUnitId] = useState<number | null>(draft?.unitId ?? null);   // đơn vị chứa cho đợt nhập
  useEffect(() => { listUnits().then((u) => { setUnits(u); if (u[0] && unitId == null) setUnitId(u[0].id); }).catch(() => {}); }, []);
  // Công thức nguyên liệu của SP này + thùng NL người dùng chọn để tiêu hao
  const [recipe, setRecipe] = useState<RecipeLine[]>([]);
  const [consumePicks, setConsumePicks] = useState<Record<string, { box_id: number; quantity: number }[]>>(draft?.consumePicks || {});
  const [pickIng, setPickIng] = useState<string | null>(null);   // mã NL đang mở popup chọn thùng
  const [prodUnit, setProdUnit] = useState("cây");                 // đơn vị SP (cây/gói…)
  const unitName = units.find((u) => u.id === unitId)?.name || "Thùng";   // đơn vị chứa (Thùng/Kiện/Hũ)
  const unitLow = unitName.toLowerCase();
  useEffect(() => {
    if (prodCode) getRecipe(prodCode).then((r) => { setRecipe(r.recipe); setProdUnit(r.unit); }).catch(() => { setRecipe([]); setProdUnit("cây"); });
    else { setRecipe([]); setProdUnit("cây"); }
  }, [prodCode]);
  const produced = (() => {
    const n = parseFloat((amount || "").replace(",", ".")), c = Math.floor(parseFloat((count || "").replace(",", ".")));
    return isFinite(n) && n > 0 && isFinite(c) && c > 0 ? n * c : 0;
  })();
  const chosenOf = (code: string) => (consumePicks[code] || []).reduce((s, p) => s + p.quantity, 0);
  // Nguyên liệu theo LOẠI PHIẾU: SẢN XUẤT → không cần NL (ẩn luôn phần chọn);
  // ĐÓNG GÓI → bắt buộc có công thức + chọn đủ thùng cho MỌI nguyên liệu.
  const packing = (slip.kind || "san_xuat") === "dong_goi";
  const recipeOk = !packing
    || (recipe.length > 0 && produced > 0 && recipe.every((l) => chosenOf(l.ingredient_code) + 1e-6 >= l.ratio * produced));
  const createUnitPick = async (name: string) => {
    try {
      const u = await createUnit(name);
      setUnits((prev) => (prev.some((x) => x.id === u.id) ? prev : [...prev, u]));
      setUnitId(u.id);
    } catch { /* im */ }
  };
  const [places, setPlaces] = useState<Place[]>([]);
  const [placeId, setPlaceId] = useState<number | null>(draft?.placeId ?? null);   // vị trí kho cho thùng mới
  // Lưu nháp mỗi khi form đổi — thoát trang quay lại là nhập tiếp
  useEffect(() => {
    boxDrafts.set(threadId, { prodCode, amount, count, note, mfgDate, unitId, placeId, consumePicks });
  }, [threadId, prodCode, amount, count, note, mfgDate, unitId, placeId, consumePicks]);
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
      const bs = await slipBoxes(threadId);
      // sắp theo NGÀY TẠO mới→cũ (created_at; id làm mốc phụ)
      bs.sort((a, b) => (b.created_at || "").localeCompare(a.created_at || "") || (b.id - a.id));
      setMyBoxes(bs);
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

  // TẠO thùng SAU khi đã có ảnh (buffer từ camera). caps rỗng + requirePhoto ⇒ không
  // tạo gì (chống thùng "trắng"). Không camera (HTTP) gọi requirePhoto=false → tạo như cũ.
  const finalizeCreate = async (caps: Processed[], requirePhoto = true) => {
    const pc = pendingCreate;
    if (!pc) return;
    setPendingCreate(null);
    setCamBases(null);
    if (requirePhoto && caps.length === 0) {
      setMsg("Chưa chụp ảnh — chưa tạo thùng. Bấm “Nhập” để làm lại.");
      toast("⚠ Chưa chụp ảnh — thùng CHƯA được tạo", "err");
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      const r = await addProductionBoxes(threadId, pc.picks, pc.note, pc.mfgDate, pc.unitId, pc.consume, pc.prodCode, pc.placeId);
      setAmount(""); setCount("1"); setNote(""); setConsumePicks({});
      if (r?._queued) {
        setMsg("⏳ Đã lưu tạm (mất mạng), sẽ gửi lại");
        return;
      }
      const boxes = r.boxes || [];
      // Upload ảnh đã buffer vào PHIẾU + từng thùng mới
      if (caps.length && boxes.length) {
        const bases = [`/api/media/production/${threadId}`, ...boxes.map((b) => `/api/media/box/${b.id}`)];
        for (const p of caps) await Promise.allSettled(bases.map((b) => uploadProcessed(b, p)));
      }
      const nc = (r.consumed || []).length;
      setMsg(`✅ Đã nhập ${pc.count} ${unitLow}${caps.length ? ` · ${caps.length} ảnh` : ""}${nc ? ` · trừ ${nc} phần nguyên liệu` : ""}`);
      onChanged();
      loadMine();
      if (boxes.length) setCodeBoxes(boxes);
    } catch (e: any) {
      setMsg(e?.message || "Lỗi nhập thùng");
    } finally {
      setBusy(false);
    }
  };

  const submit = async () => {
    const n = parseFloat(amount.replace(",", "."));
    if (!isFinite(n) || n <= 0) {
      setMsg(`Số ${prodUnit} không hợp lệ`);
      return;
    }
    const c = Math.floor(parseFloat(count.replace(",", ".")));
    if (!isFinite(c) || c <= 0) {
      setMsg(`Số ${unitLow} không hợp lệ`);
      return;
    }
    if (!recipeOk) {
      setMsg(recipe.length === 0
        ? "⚠ Phiếu đóng gói bắt buộc trừ nguyên liệu — SP chưa có công thức"
        : "⚠ Chọn đủ thùng nguyên liệu trước khi tạo thùng");
      return;
    }
    // Ảnh BẮT BUỘC: xác nhận rồi mở camera CHỤP TRƯỚC (buffer). ĐÓNG camera có ≥1 ảnh
    // mới TẠO thùng (finalizeCreate); bấm quay lại / xong mà chưa chụp → KHÔNG tạo gì.
    if (!(await confirmDialog(`Nhập ${c} ${unitLow} × ${soVN(n)} ${prodUnit} ${prodCode}?\nBước sau chụp ảnh thùng — chưa chụp thì chưa tạo.`))) return;
    const picks = Array.from({ length: c }, () => ({ quantity: n }));  // c thùng giống nhau
    const consume = Object.values(consumePicks).flat();               // thùng NL đã chọn
    capturedRef.current = [];
    setPendingCreate({ picks, note: note.trim(), mfgDate, unitId, consume, prodCode, placeId, count: c });
    setMsg("");
    if (cameraSupported()) {
      setCamBases([`/api/media/production/${threadId}`]);   // COLLECT: base chỉ để mở khung, upload ở finalize
    } else {
      // Không có camera (HTTP) → không ép ảnh được; tạo luôn như cũ (không ảnh).
      await finalizeCreate([], false);
    }
  };

  const cnt = Math.max(1, Math.floor(parseFloat((count || "1").replace(",", ".")) || 1));
  return (
    <section class="card">
      {locked ? (
        <div class="muted small pb-lock"><Icon name="lock" size={14} /> Phiếu đã khoá — không nhập thùng mới. Chỉ trao đổi được.</div>
      ) : (
      <>
      <label class="card-label"><Icon name="box" size={16} /> Nhập {unitLow}</label>

      <div class="pb-form">
        <span class="pb-lb"><Icon name="tag" size={15} /> Sản phẩm</span>
        <div class="pb-ctl">
          <PickerPopup value={prodCode} placeholder="Chọn SP" allowFreeText
            onSearch={async (q): Promise<PickOpt[]> => (await searchProducts(q).catch(() => [])).map((s) => ({ key: s.code, label: s.code, sub: s.name || undefined }))}
            onPick={(o) => setProdCode(o.key)} />
        </div>

        <span class="pb-lb"><Icon name="calendar" size={15} /> NSX</span>
        <div class="pb-ctl">
          <input type="date" value={mfgDate} disabled={!hasSp}
            onInput={(e) => setMfgDate((e.target as HTMLInputElement).value)} />
        </div>

        <span class="pb-lb"><Icon name="box" size={15} /> Đơn vị</span>
        <div class="pb-ctl">
          <SelectPopup title="Đơn vị chứa" searchable onCreate={createUnitPick} disabled={!hasSp}
            value={unitId ?? ""} options={units.map((u) => ({ value: u.id, label: u.name }))}
            onChange={(v) => setUnitId(v ? Number(v) : null)} />
        </div>

        <span class="pb-lb"><Icon name="tag" size={15} /> Vị trí</span>
        <div class="pb-ctl">
          <SelectPopup title="Vị trí kho" placeholder="— Chưa xếp —" searchable onCreate={createPlacePick} disabled={!hasSp}
            value={placeId ?? ""}
            options={[{ value: "", label: "— Chưa xếp —" }, ...places.map((p) => ({ value: p.id, label: p.name }))]}
            onChange={(v) => setPlaceId(v ? Number(v) : null)} />
        </div>

        <span class="pb-lb"><Icon name="clipboard" size={15} /> Số lượng</span>
        <div class="pb-ctl pb-qty">
          <input type="text" inputMode="numeric" class="pb-count" value={count} disabled={!hasSp}
            onFocus={(e) => (e.target as HTMLInputElement).select()}
            onInput={(e) => setCount((e.target as HTMLInputElement).value)}
            placeholder="1" title={`Số ${unitLow} giống nhau`} />
          <span class="pb-x">{unitLow} ×</span>
          <input type="text" inputMode="decimal" class="pb-amount" value={amount} disabled={!hasSp}
            onFocus={(e) => (e.target as HTMLInputElement).select()}
            onInput={(e) => setAmount((e.target as HTMLInputElement).value)}
            placeholder={`Số ${prodUnit}`} />
        </div>

        <span class="pb-lb"><Icon name="note" size={15} /> Ghi chú</span>
        <div class="pb-ctl">
          <input type="text" value={note} disabled={!hasSp}
            onInput={(e) => setNote((e.target as HTMLInputElement).value)}
            placeholder="Tuỳ chọn" />
        </div>
      </div>

      {!hasSp && <div class="muted small pb-hint">Chọn sản phẩm trước khi nhập.</div>}

      {packing && recipe.length > 0 && (
        <div class={"recipe-consume" + (recipeOk && produced > 0 ? " ok" : "")}>
          <div class="card-label"><Icon name="leaf" size={15} /> Nguyên liệu cần trừ {produced > 0 ? `(SX ${soVN(produced)} ${prodUnit})` : ""}</div>
          {produced <= 0 && <div class="muted small">Nhập số {unitLow} × số {prodUnit} trước để tính nguyên liệu.</div>}
          {recipe.map((l) => {
            const need = +(l.ratio * produced).toFixed(3);
            const chosen = chosenOf(l.ingredient_code);
            const enough = need > 0 && chosen >= need;
            return (
              <div class="stock-head" key={l.ingredient_code}>
                <b>{l.ingredient_code}</b>
                <span class={enough ? "inv-pick-sum ok" : "inv-pick-sum"}>{soVN(chosen)}/{soVN(need)}</span>
                <span class="muted small">tồn {soVN(l.stock ?? 0)}</span>
                <button class="btn small" disabled={!hasSp || produced <= 0} onClick={() => setPickIng(l.ingredient_code)}>Chọn thùng</button>
              </div>
            );
          })}
        </div>
      )}
      {packing && hasSp && recipe.length === 0 && (
        <div class="muted small pb-hint">⚠ Phiếu đóng gói bắt buộc trừ nguyên liệu — {prodCode} chưa có công thức. Thêm ở trang chi tiết sản phẩm.</div>
      )}

      <button class="btn primary block pb-submit" disabled={!hasSp || busy || !recipeOk} onClick={submit}
        title={!recipeOk ? "Chọn đủ thùng nguyên liệu trước" : undefined}>
        <Icon name="plus" size={16} /> {busy ? "Đang nhập…" : `Nhập ${cnt} ${unitLow}${produced > 0 ? ` · ${soVN(produced * cnt)} ${prodUnit}` : ""}`}
      </button>
      {packing && recipe.length > 0 && produced > 0 && !recipeOk && (
        <div class="muted small pb-hint">⚠ Cần chọn đủ thùng nguyên liệu mới tạo được thùng.</div>
      )}
      {msg && <div class="muted small pb-hint">{msg}</div>}
      </>
      )}

      {camBases && (
        <CameraBox base={camBases[0]}
          onCapture={(p) => { capturedRef.current.push(p); }}
          onUploaded={() => {}}
          onClose={() => finalizeCreate(capturedRef.current)} />
      )}

      {codeBoxes && (
        <div class="cam-overlay">
          <div class="pb-codes-pop">
            <div class="pb-codes-title">✍️ Hãy ghi lên thùng trước khi đóng popup này</div>
            <BoxLabelGrid boxes={codeBoxes as any} />
            <button class="btn primary block" onClick={() => setCodeBoxes(null)}>Đã ghi xong</button>
          </div>
        </div>
      )}

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
          <div class="inv-total pb-mine-head">
            <span>Đã nhập ở phiếu này ({myBoxes.length})</span>
            <div class="pb-viewtog">
              <button class={"pb-vt" + (mineView === "grid" ? " on" : "")} title="Lưới tem" onClick={() => setMineView("grid")}><Icon name="box" size={15} /></button>
              <button class={"pb-vt" + (mineView === "list" ? " on" : "")} title="Danh sách" onClick={() => setMineView("list")}><Icon name="menu" size={15} /></button>
            </div>
          </div>
          {mineView === "grid" ? <BoxLabelGrid boxes={myBoxes as any} /> : (
            <div class="pb-boxlist">
              {myBoxes.map((b) => {
                const rm = b.remaining ?? b.quantity;
                const used = b.allocated ?? 0;
                return (
                  <a class={"pb-blrow" + (b.disabled ? " off" : "")} href={`#/thung/${b.id}`} key={b.id}>
                    <span class="pb-blcode">{b.box_code}</span>
                    <span class="pb-blsp">{b.product_code}</span>
                    <span class="pb-blq">{soVN(rm)}{used > 0 ? <span class="muted">/{soVN(b.quantity)}</span> : ""} <span class="muted small">{b.product_unit || "cây"}</span></span>
                    {b.place_name && <span class="pb-blplace">{b.place_name}</span>}
                    {b.created_by && <span class="pb-blby muted small"><Icon name="user" size={12} /> {b.created_by}</span>}
                    {b.disabled ? <span class="pb-bloff">vô hiệu</span> : null}
                  </a>
                );
              })}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
