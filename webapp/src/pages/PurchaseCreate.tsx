// Trang TẠO phiếu nhập hàng (#/nhap-hang/tao, mọi người dùng) — thay popup cũ.
// Chọn NCC (autocomplete, gõ tên lạ → tạo NCC mới ngay; ?ncc=<id> = prefill từ
// trang NCC), dòng hàng: SP × SL × giá + đơn vị nhập (PurchaseUnitPicker).
// NHÁP TỰ LƯU localStorage (purchase_create_draft_v1): rời trang giữa chừng →
// quay lại khôi phục nguyên trạng; tạo xong / Xoá nháp mới xoá. POST /api/purchases.
import { useEffect, useRef, useState } from "preact/hooks";
import { PageHead } from "../ui/PageHead";
import {
  createProduct, createPurchase, createSupplier, listSuppliers,
  searchProducts, soVN, type Supplier,
} from "../api";
import { buildPurchaseProductOptions, isCreateProd, codeFromCreateKey, unitChoicesFor, type UnitChoice } from "../detail/purchaseProduct";
import { PurchaseUnitPicker } from "../detail/PurchaseUnitPicker";
import { foldVN, parseMoney, parseQty } from "../format";
import { PickerPopup, type PickOpt } from "../ui/PickerPopup";
import { confirmDialog, toast } from "../ui/feedback";
import { Icon } from "../ui/Icon";

type Line = { sp: string; sl: string; price: string; unit?: string; factor?: number };
type Picked = { id: number; name: string } | null;
const NEW_PREFIX = "__new__:";
const DRAFT_KEY = "purchase_create_draft_v1";
const BLANK: Line = { sp: "", sl: "1", price: "" };

const hasContent = (picked: Picked, lines: Line[], note: string) =>
  !!picked || !!note.trim() ||
  lines.some((l) => l.sp.trim() || l.price.trim() || (l.sl.trim() && l.sl.trim() !== "1"));

function readDraft(): { picked: Picked; lines: Line[]; note: string } | null {
  try {
    const d = JSON.parse(localStorage.getItem(DRAFT_KEY) || "");
    if (!d || !Array.isArray(d.lines)) return null;
    return { picked: d.picked || null, lines: d.lines, note: d.note || "" };
  } catch { return null; }
}

export function PurchaseCreate() {
  // Tạo phiếu nhập mở cho MỌI người dùng đăng nhập (2026-07-17) — không gate office.
  // ?ncc=<id> → prefill NCC (ưu tiên hơn NCC trong nháp)
  const nccParam = Number((window.location.hash.match(/[?&]ncc=(\d+)/) || [])[1] || 0) || null;
  const draft = useRef(readDraft()).current;
  const [picked, setPicked] = useState<Picked>(nccParam ? { id: nccParam, name: `NCC #${nccParam}` } : draft?.picked || null);
  const [lines, setLines] = useState<Line[]>(draft?.lines?.length ? draft.lines : [{ ...BLANK }]);
  const [note, setNote] = useState(draft?.note || "");
  const [restored] = useState(!!draft && hasContent(nccParam ? null : draft.picked, draft.lines, draft.note));
  const [busy, setBusy] = useState(false);

  // đơn vị nhập theo mã SP: gốc + quy đổi (product_units) — nạp khi chọn/khôi phục SP
  const [unitsBySp, setUnitsBySp] = useState<Record<string, UnitChoice[]>>({});
  const loadUnits = (sp: string) => {
    const key = sp.trim().toUpperCase();
    if (!key) return;
    setUnitsBySp((m) => { if (m[key]) return m; unitChoicesFor(key).then((cs) => setUnitsBySp((n) => ({ ...n, [key]: cs }))); return m; });
  };
  useEffect(() => { lines.forEach((l) => loadUnits(l.sp)); }, []);   // nháp khôi phục → nạp đơn vị

  // Tra tên NCC thật cho ?ncc= (không cần truyền tên qua URL)
  useEffect(() => {
    if (!nccParam) return;
    listSuppliers().then((all) => {
      const s = all.find((x) => x.id === nccParam);
      if (s) setPicked({ id: s.id, name: s.name });
    }).catch(() => {});
  }, [nccParam]);

  // NHÁP tự lưu: có nội dung → ghi; trống → xoá key (khỏi khôi phục nháp rỗng)
  useEffect(() => {
    if (hasContent(picked, lines, note)) {
      localStorage.setItem(DRAFT_KEY, JSON.stringify({ picked, lines, note, at: Date.now() }));
    } else {
      localStorage.removeItem(DRAFT_KEY);
    }
  }, [picked, lines, note]);

  const clearDraft = () => {
    localStorage.removeItem(DRAFT_KEY);
    setPicked(nccParam ? picked : null);
    setLines([{ ...BLANK }]);
    setNote("");
    toast("Đã xoá nháp", "ok");
  };

  const searchSuppliersOpts = async (q: string): Promise<PickOpt[]> => {
    const all: Supplier[] = await listSuppliers().catch(() => []);
    const fq = foldVN(q.trim());
    const hit = !fq ? all : all.filter((s) => foldVN(`${s.name} ${s.phone || ""}`).includes(fq));
    const opts: PickOpt[] = hit.map((s) => ({ key: String(s.id), label: s.name, sub: s.phone || undefined }));
    // gõ tên chưa có → cho tạo NCC mới ngay trong trang
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
    .map((l) => ({
      sp: l.sp.trim().toUpperCase(), sl: parseQty(l.sl),
      price: parseMoney(l.price),
      // đơn vị nhập khác gốc → snapshot vào item (SL + giá tính theo đơn vị đó)
      ...(l.unit && (l.factor || 0) > 0 && l.factor !== 1 ? { unit: l.unit, unit_factor: l.factor } : {}),
    }))
    .filter((l) => l.sp && isFinite(l.sl) && l.sl > 0 && isFinite(l.price) && l.price >= 0);
  const total = parsed.reduce((s, l) => s + l.sl * l.price, 0);

  const submit = async () => {
    if (!picked) return toast("Chọn nhà cung cấp trước", "info");
    if (!parsed.length) return toast("Nhập ít nhất 1 dòng hàng (SP + SL + giá)", "info");
    if (!(await confirmDialog(`Tạo phiếu nhập ${soVN(total)}đ từ ${picked.name}?`))) return;
    setBusy(true);
    try {
      const r = await createPurchase(picked.id, parsed, note.trim());
      localStorage.removeItem(DRAFT_KEY);   // hoàn thành → hết nháp
      toast("Đã tạo phiếu nhập", "ok");
      const pid = r?.purchase?.id;
      // Prompt: nhập KHO hàng mua về ngay? — mở modal ở trang chi tiết (cờ session).
      if (pid && await confirmDialog("Nhập kho hàng mua về ngay? (tạo thùng / cộng vào thùng có sẵn)",
        { okLabel: "Nhập kho ngay", cancelLabel: "Để sau" })) {
        sessionStorage.setItem("pg_open", String(pid));
      }
      window.location.hash = pid ? `#/nhap-hang/${pid}` : "#/nhap-hang";
    } catch (e: any) {
      toast(e?.message || "Lỗi tạo phiếu nhập", "err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div class="pur-edit-page">
      <PageHead fallback="#/nhap-hang"
        title={<><Icon name="truck" size={18} /> Tạo phiếu nhập hàng</>}
        sub={picked ? picked.name : "Chưa chọn nhà cung cấp"} />

      {restored && (
        <div class="card pur-draft-hint">
          <span class="muted small"><Icon name="edit" size={13} /> Đã khôi phục nháp chưa hoàn thành.</span>
          <button class="btn small" onClick={clearDraft}>Xoá nháp</button>
        </div>
      )}

      <section class="card pur-edit-card">
        <div class="card-label"><Icon name="users" size={15} /> Nhà cung cấp</div>
        {!nccParam && (
          <PickerPopup value={picked?.name || ""} placeholder="Chọn nhà cung cấp"
            onSearch={searchSuppliersOpts} onPick={pickSupplier} />
        )}
        {nccParam && <div class="muted small">NCC: <b>{picked?.name}</b></div>}
      </section>

      <section class="card pur-edit-card">
        <div class="card-label"><Icon name="box" size={15} /> Hàng nhập</div>
        <div class="ret-sheet">
          {lines.map((l, i) => (
            <div class="ret-line" key={i}>
              <div class="ret-sp">
                <PickerPopup value={l.sp} placeholder="Mã SP"
                  onSearch={async (q) => buildPurchaseProductOptions(await searchProducts(q).catch(() => []), q)}
                  onPick={async (o) => {
                    if (isCreateProd(o.key)) {
                      const code = codeFromCreateKey(o.key);
                      try { await createProduct(code); upd(i, { sp: code, unit: undefined, factor: undefined }); loadUnits(code); toast(`Đã tạo mã hàng "${code}"`, "ok"); }
                      catch (e: any) { toast(e?.message || "Lỗi tạo mã hàng", "err"); }
                    } else { upd(i, { sp: o.key, unit: undefined, factor: undefined }); loadUnits(o.key); }
                  }} />
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
              <PurchaseUnitPicker code={l.sp} line={l} choices={unitsBySp[l.sp.trim().toUpperCase()]}
                onChoices={(k, list) => setUnitsBySp((m) => ({ ...m, [k]: list }))}
                onPick={(u) => upd(i, u.factor === 1 ? { unit: undefined, factor: undefined } : { unit: u.name, factor: u.factor })} />
            </div>
          ))}
          <button class="btn small" onClick={() => setLines((prev) => [...prev, { ...BLANK }])}>
            <Icon name="plus" size={14} /> Thêm dòng
          </button>
          <input type="text" placeholder="Ghi chú (tuỳ chọn)" value={note}
            onInput={(e) => setNote((e.target as HTMLInputElement).value)} />
          <div class="ret-total">Tổng nhập: <b>{soVN(total)}đ</b></div>
          <div class="row pur-edit-actions">
            <a class="btn" href="#/nhap-hang">Đóng</a>
            <button class="btn primary" disabled={busy || !parsed.length} onClick={submit}>
              {busy ? "Đang tạo…" : "Tạo phiếu nhập"}
            </button>
          </div>
          <p class="muted small pur-draft-note">Nội dung tự lưu nháp — rời trang giữa chừng, quay lại vẫn còn.</p>
        </div>
      </section>
    </div>
  );
}
