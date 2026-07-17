// Chi tiết kho 1 product — danh sách mọi thùng + tình trạng (Trong kho / Đã xuất
// đơn #x / Đã giao). GET /api/inventory/:code (all_boxes). Nhóm tồn theo size ở đầu.
// Thùng đã xuất link tới đơn. Realtime production_changed → tải lại.
import { useEffect, useRef, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { inventoryDetail, productOrders, searchKiotvietProducts, linkProductKiotviet, unlinkProductKiotviet, createKiotvietProduct, createProduct, kiotvietCategories, deleteProduct, updateProduct, renameProduct, getRecipe, currentUser, soVN, type InvDetail, type InvBox, type InvOrderRef, type KvProduct, type KvCategory } from "../api";
import { SelectPopup } from "../ui/SelectPopup";
import { confirmDialog, toast } from "../ui/feedback";
import { useScrollLock } from "../useScrollLock";
import { money } from "../format";
import { onRealtime } from "../realtime";
import { Loading, ErrorState, LoadingInline } from "../ui/states";
import { Icon } from "../ui/Icon";
import { BoxLabelGrid } from "../detail/BoxLabelGrid";
import { CompactBoxList } from "../detail/CompactBoxList";
import { RecipeEditor } from "../detail/RecipeEditor";
import { ProductUnits } from "../detail/ProductUnits";
import { History } from "../detail/History";
import { usePopupBack } from "../ui/usePopupBack";
import { BoxViewToggle, useBoxView } from "../detail/BoxViewToggle";

export function InventoryDetail({ code }: { code: string }) {
  const [inv, setInv] = useState<InvDetail | null>(null);
  const [err, setErr] = useState("");
  const isAdmin = currentUser()?.role === "admin";
  // Có công thức chưa? — cảnh báo khi bật Đóng gói mà SP chưa khai công thức.
  const [hasRecipe, setHasRecipe] = useState<boolean | null>(null);
  useEffect(() => {
    let live = true;
    getRecipe(code).then((r) => { if (live) setHasRecipe((r.recipe || []).length > 0); }).catch(() => { if (live) setHasRecipe(null); });
    return () => { live = false; };
  }, [code, inv?.product?.can_package]);
  const [unitInput, setUnitInput] = useState("");
  const [unitSaved, setUnitSaved] = useState(false);
  useEffect(() => { setUnitInput(inv?.product?.unit || "cây"); }, [inv?.product?.unit]);
  const saveUnit = async (val?: string) => {
    const u = (val ?? unitInput).trim() || "cây";
    setUnitInput(u);
    if (!inv?.product || u === (inv.product.unit || "cây")) return;
    try {
      const p = await updateProduct(code, { unit: u });
      if (p && inv) { setInv({ ...inv, product: p }); setUnitSaved(true); setTimeout(() => setUnitSaved(false), 1500); }
      // GỢI Ý (không tự suy nữa): đơn vị đếm thùng/kiện thường là SP nguyên kiện →
      // đề nghị gán vai 📦 cho đơn vị gốc (docs/plan-don-vi-hang-hoa.md)
      if (p && !p.self_container && ["thùng", "kiện"].includes(u.toLowerCase())
          && (await confirmDialog(`Đơn vị "${u}" thường là SP NGUYÊN KIỆN (mỗi ${u} = 1 thùng riêng, nhập kho khỏi chọn đơn vị chứa). Bật vai 📦 nguyên kiện?`))) {
        const p2 = await updateProduct(code, { bulk_unit_id: 0 });
        if (p2) { setInv((cur) => cur ? { ...cur, product: p2 } : cur); toast("Đã bật vai nguyên kiện (đơn vị gốc)", "ok"); }
      }
    } catch { /* im */ }
  };
  // Tồn kho tối thiểu (ngưỡng cảnh báo) — sửa như Đơn vị (blur là lưu)
  const [minInput, setMinInput] = useState("");
  const [minSaved, setMinSaved] = useState(false);
  useEffect(() => { setMinInput(inv?.product?.min_stock ? String(inv.product.min_stock) : ""); }, [inv?.product?.min_stock]);
  const saveMin = async () => {
    const v = minInput.trim() === "" ? 0 : Number(minInput);
    if (!inv?.product || isNaN(v) || v === (inv.product.min_stock || 0)) return;
    try {
      const p = await updateProduct(code, { min_stock: v });
      if (p && inv) { setInv({ ...inv, product: p }); setMinSaved(true); setTimeout(() => setMinSaved(false), 1500); }
    } catch { /* im */ }
  };
  // Mã SP — đổi TỰ DO (admin): mọi liên kết theo products.id nên chỉ đổi nhãn;
  // mã cũ thành alias (gõ vẫn nhận, link cũ redirect). Có confirm vì đổi cả KiotViet.
  const [codeInput, setCodeInput] = useState("");
  useEffect(() => { setCodeInput(inv?.product_code || code); }, [inv?.product_code]);
  const saveCode = async () => {
    const nc = codeInput.trim().toUpperCase();
    if (!inv || !nc || nc === (inv.product_code || code)) { setCodeInput(inv?.product_code || code); return; }
    const ok = await confirmDialog(
      `Đổi mã "${inv.product_code}" → "${nc}"?\nĐơn cũ, kho, bảng giá, SX sẽ hiện mã mới ngay.` +
      (inv.product?.linked ? "\nMã bên KiotViet cũng được đổi theo." : ""));
    if (!ok) { setCodeInput(inv.product_code || code); return; }
    try {
      const r = await renameProduct(inv.product_code || code, nc);
      toast(`✅ Đã đổi mã → ${r.product.code}` + (r.kiotviet ? `\n${r.kiotviet}` : ""), "ok");
      window.location.replace(`#/kho/${encodeURIComponent(r.product.code)}`);
    } catch (e: any) {
      toast(e?.message || "Đổi mã lỗi", "err");
      setCodeInput(inv.product_code || code);
    }
  };
  // Tên SP — sửa tại chỗ như Đơn vị (blur là lưu)
  const [nameInput, setNameInput] = useState("");
  const [nameSaved, setNameSaved] = useState(false);
  useEffect(() => { setNameInput(inv?.product?.name || ""); }, [inv?.product?.name]);
  const saveName = async () => {
    const n = nameInput.trim();
    if (!inv?.product || n === (inv.product.name || "")) return;
    try {
      const p = await updateProduct(code, { name: n });
      if (p && inv) { setInv({ ...inv, product: p }); setNameSaved(true); setTimeout(() => setNameSaved(false), 1500); }
    } catch { /* im */ }
  };
  // Cách sản xuất = 2 CỜ ĐỘC LẬP: SX trực tiếp (phiếu san_xuat) và Đóng gói từ NL
  // (phiếu dong_goi). 1 SP có thể bật cả hai / không cái nào (nguyên liệu / hàng mua).
  const toggleMethod = async (key: "can_produce_directly" | "can_package") => {
    if (!inv?.product) return;
    const next = !inv.product[key];
    try {
      const p = await updateProduct(code, { [key]: next });
      if (p && inv) {
        setInv({ ...inv, product: p });
        const label = key === "can_produce_directly" ? "sản xuất trực tiếp" : "đóng gói từ nguyên liệu";
        toast(next ? `✅ Bật ${label}` : `⭘ Tắt ${label}`, "ok");
      }
    } catch (e: any) { toast(e?.message || "Lỗi", "err"); }
  };
  // Có thể BÁN / có thể NHẬP — gate gợi ý SP ở hoá đơn bán & phiếu nhập NCC
  const toggleTrade = async (key: "can_sell" | "can_purchase") => {
    if (!inv?.product) return;
    const next = !(inv.product[key] !== false);
    try {
      const p = await updateProduct(code, { [key]: next });
      if (p && inv) {
        setInv({ ...inv, product: p });
        const label = key === "can_sell" ? "bán" : "nhập";
        toast(next ? `✅ SP có thể ${label}` : `🚫 SP tắt ${label} — không gợi ý ở picker ${label} nữa`, "ok");
      }
    } catch (e: any) { toast(e?.message || "Lỗi", "err"); }
  };
  // Liên kết KiotViet từng cái (modal tìm + chọn)
  const [linkOpen, setLinkOpen] = useState(false);
  const [kvQ, setKvQ] = useState("");
  const [kvRes, setKvRes] = useState<KvProduct[]>([]);
  const [kvLoading, setKvLoading] = useState(false);
  useScrollLock(linkOpen);
  usePopupBack(linkOpen, () => setLinkOpen(false));
  useEffect(() => {
    if (!linkOpen) return;
    const q = kvQ.trim();
    if (q.length < 2) { setKvRes([]); return; }
    let alive = true;
    setKvLoading(true);
    const t = setTimeout(() => {
      searchKiotvietProducts(q)
        .then((r) => { if (alive) setKvRes(r); })
        .catch(() => { if (alive) setKvRes([]); })
        .finally(() => { if (alive) setKvLoading(false); });
    }, 300);
    return () => { alive = false; clearTimeout(t); };
  }, [kvQ, linkOpen]);

  // Đơn có SP này — LAZY: chỉ tải khi cuộn tới khối, phân trang "Xem thêm"
  const [ords, setOrds] = useState<InvOrderRef[]>([]);
  const [ordTotal, setOrdTotal] = useState(0);
  const [ordMore, setOrdMore] = useState(false);
  const [ordLoading, setOrdLoading] = useState(false);
  const ordStarted = useRef(false);
  const ordSecRef = useRef<HTMLElement>(null);

  const loadOrders = async (reset: boolean) => {
    setOrdLoading(true);
    const offset = reset ? 0 : ords.length;
    try {
      const r = await productOrders(code, offset, 20);
      setOrds((prev) => (reset ? r.orders : [...prev, ...r.orders]));
      setOrdTotal(r.total);
      setOrdMore(r.has_more);
    } catch { /* im */ } finally {
      setOrdLoading(false);
    }
  };

  // Đổi mã SP → reset khối đơn.
  useEffect(() => {
    ordStarted.current = false;
    setOrds([]); setOrdTotal(0); setOrdMore(false);
  }, [code]);

  // Gắn IntersectionObserver SAU khi khối render (inv đã tải) → tự tải lần đầu khi lộ.
  useEffect(() => {
    const el = ordSecRef.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting && !ordStarted.current) {
        ordStarted.current = true;
        loadOrders(true);
      }
    }, { rootMargin: "200px" });
    io.observe(el);
    return () => io.disconnect();
  }, [inv, code]);

  const openLink = () => { setKvQ(inv?.product?.name || code); setLinkOpen(true); };
  const doLink = async (kv: KvProduct) => {
    try {
      await linkProductKiotviet(code, kv.id, kv.full_name);
      toast(`✅ Liên kết ${code} → ${kv.full_name}`, "ok");
      setLinkOpen(false);
      await load();
    } catch (e: any) {
      toast(e?.message || "Liên kết lỗi", "err");
    }
  };
  const [kvCreating, setKvCreating] = useState(false);
  const [showEmpty, setShowEmpty] = useState(false);   // thùng đã hết: mặc định ẩn, có nút bật
  // nhớ kiểu xem thùng ở chi tiết SP (mặc định Ô THÙNG)
  const [invView, setInvView] = useBoxView("inv_detail", "grid");
  const [kvCatOpen, setKvCatOpen] = useState(false);
  const [kvCats, setKvCats] = useState<KvCategory[]>([]);
  const [kvCatId, setKvCatId] = useState("");
  useScrollLock(kvCatOpen);
  usePopupBack(kvCatOpen, () => setKvCatOpen(false));
  const openKvCreate = async () => {
    setKvCatOpen(true);
    if (!kvCats.length) {
      try { setKvCats(await kiotvietCategories()); }
      catch (e: any) { toast(e?.message || "Không lấy được nhóm hàng", "err"); }
    }
  };
  const doKvCreate = async () => {
    if (!kvCatId) { toast("Chọn nhóm hàng", "err"); return; }
    setKvCreating(true);
    try {
      const p = await createKiotvietProduct(code, { category_id: Number(kvCatId) });
      if (p && inv) setInv({ ...inv, product: p });
      setKvCatOpen(false);
      toast("✅ Đã tạo + liên kết KiotViet", "ok");
    } catch (e: any) {
      toast(e?.message || "Lỗi tạo KiotViet", "err");
    } finally {
      setKvCreating(false);
    }
  };

  const doUnlink = async () => {
    if (!(await confirmDialog("Bỏ liên kết KiotViet của mã này?"))) return;
    try {
      await unlinkProductKiotviet(code);
      toast("Đã bỏ liên kết", "ok");
      await load();
    } catch (e: any) {
      toast(e?.message || "Lỗi", "err");
    }
  };
  const doDelete = async () => {
    if (!(await confirmDialog(`Xoá mã "${code}" khỏi danh mục?\n(Không ảnh hưởng đơn/thùng đã có)`, { danger: true }))) return;
    try {
      await deleteProduct(code);
      toast(`🗑️ Đã xoá mã ${code}`, "ok");
      window.location.hash = "#/kho";
    } catch (e: any) {
      toast(e?.message || "Xoá lỗi", "err");
    }
  };

  const load = async () => {
    try {
      const r = await inventoryDetail(code);
      // URL mang MÃ CŨ (đã đổi) → server resolve, mình thay URL sang mã hiện hành
      if (r.product_code && r.product_code !== code) {
        window.location.replace(`#/kho/${encodeURIComponent(r.product_code)}`);
        return;
      }
      setInv(r);
    } catch (e: any) {
      setErr(e?.message || "Lỗi tải");
    }
  };
  useEffect(() => {
    load();
  }, [code]);
  useEffect(
    () =>
      onRealtime((e) => {
        if (e.type === "resync" || e.type === "production_changed" || e.type === "inventory_changed" || e.type === "box_changed" || e.type === "order_changed") {
          load();
          if (ordStarted.current) loadOrders(true);   // đơn có SP có thể đổi
        }
      }),
    [code]
  );

  if (err) return <ErrorState msg={err} onRetry={load} />;
  if (!inv) return <Loading />;
  const all: InvBox[] = inv.all_boxes;

  return (
    <div class="inv-detail">
      <div class="prod-detail-head inv-head">
        <BackLink fallback="#/kho" />
        <div class="inv-head-title">
          <div class="prod-sp big">{inv.product_code}</div>
          <div class="prod-date muted">{inv.box_count} thùng</div>
        </div>
        <div class="inv-stock-big">
          <span class="inv-stock-num">{soVN(inv.total)}</span>
          <span class="inv-stock-lbl">tồn kho</span>
        </div>
      </div>

      <a class="btn block pt-open-btn" href={`#/kho/${encodeURIComponent(code)}/timeline`}>
        <Icon name="history" size={16} /> Timeline biến động tồn →
      </a>

      {/* Tên danh mục + liên kết KiotViet */}
      <section class="card prod-link">
        {!inv.product && (
          <div class="box-kv" style={{ alignItems: "center" }}>
            <span class="muted small fill">
              Mã "{code}" chưa có trong danh mục SP (thùng tạo bằng mã gõ tự do) — thêm vào
              danh mục để sửa tên/đơn vị/đổi mã/liên kết KiotViet.
            </span>
            <button class="btn small" onClick={async () => {
              try {
                await createProduct(code);
                toast(`✅ Đã thêm ${code} vào danh mục`, "ok");
                await load();
              } catch (e: any) { toast(e?.message || "Lỗi", "err"); }
            }}>➕ Thêm vào danh mục</button>
          </div>
        )}
        {inv.product && isAdmin && (
          <div class="box-kv">
            <span class="box-k">Mã SP</span>
            <input class="box-place" style={{ minWidth: "130px", fontWeight: 700, textTransform: "uppercase" }}
              value={codeInput}
              onInput={(e: any) => setCodeInput(e.target.value)} onBlur={saveCode}
              onKeyDown={(e: any) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
          </div>
        )}
        {inv.product && (
          <div class="box-kv">
            <span class="box-k">Tên {nameSaved && <span class="muted small">✓</span>}</span>
            <input class="box-place" style={{ flex: 1, minWidth: "150px" }} value={nameInput} placeholder={code}
              onInput={(e: any) => setNameInput(e.target.value)} onBlur={saveName}
              onKeyDown={(e: any) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
          </div>
        )}
        <div class="box-kv">
          <span class="box-k">Đơn vị {unitSaved && <span class="muted small">✓</span>}</span>
          <div style={{ minWidth: "140px" }}>
            <SelectPopup title="Đơn vị đếm của SP" searchable
              onCreate={(name: string) => saveUnit(name)}
              value={unitInput}
              options={(["cây", "kg", "gói", "bịch", "hũ", "cái", "hộp", "lốc", "thùng", "kiện"].includes(unitInput)
                ? ["cây", "kg", "gói", "bịch", "hũ", "cái", "hộp", "lốc", "thùng", "kiện"]
                : [unitInput, "cây", "kg", "gói", "bịch", "hũ", "cái", "hộp", "lốc", "thùng", "kiện"].filter(Boolean))
                .map((u) => ({ value: u, label: u, sub: (u === "thùng" || u === "kiện") ? "Thường là SP nguyên kiện — gán vai 📦 ở khối Quy đổi đơn vị" : undefined }))}
              onChange={(v: string) => saveUnit(v)} />
          </div>
        </div>
        {inv.product?.self_container && (
          <div class="muted small unit-self-note" style={{ margin: "-4px 0 8px" }}>
            <Icon name="tag" size={13} /> SP <b>nguyên kiện</b> (vai 📦 ở khối Quy đổi đơn vị) — mỗi kiện = 1 thùng riêng,
            nhập kho <b>khỏi chọn đơn vị chứa</b>, và có nút <b>Trả về nguyên liệu</b> ở chi tiết thùng.
          </div>
        )}
        {inv.product && <ProductUnits code={inv.product_code || code} baseUnit={inv.product?.unit || "cây"} />}
        <div class="box-kv">
          <span class="box-k">Tồn tối thiểu {minSaved && <span class="muted small">✓</span>}</span>
          <input class="box-place" style={{ minWidth: "90px" }} type="number" inputMode="decimal" value={minInput} placeholder="0"
            onInput={(e: any) => setMinInput(e.target.value)} onBlur={saveMin}
            onKeyDown={(e: any) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
          <span class="muted small">{inv.product?.unit || "cây"}{inv.product && (inv.product.min_stock || 0) > 0 && (inv.total || 0) < (inv.product.min_stock || 0) ? <span class="min-below"> · ⚠ tồn {soVN(inv.total || 0)} dưới mức</span> : null}</span>
        </div>
        {inv.product && isAdmin && (
          <div class="box-kv">
            <span class="box-k">Cách sản xuất</span>
            <div class="row" role="group">
              <button class={"trade-chip" + (inv.product.can_produce_directly ? " on" : "")} onClick={() => toggleMethod("can_produce_directly")}>
                <Icon name="factory" size={14} /> Sản xuất trực tiếp
              </button>
              <button class={"trade-chip" + (inv.product.can_package ? " on" : "")} onClick={() => toggleMethod("can_package")}>
                <Icon name="box" size={14} /> Đóng gói từ NL
              </button>
            </div>
          </div>
        )}
        {inv.product && isAdmin && (
          <div class="muted small" style={{ margin: "-2px 0 6px" }}>
            {inv.product.can_produce_directly && inv.product.can_package
              ? "Nhập thùng được từ cả phiếu SẢN XUẤT lẫn ĐÓNG GÓI (đóng gói trừ nguyên liệu theo công thức)."
              : inv.product.can_produce_directly
              ? "Nhập thùng từ phiếu SẢN XUẤT (không trừ NL)."
              : inv.product.can_package
              ? "Chỉ nhập thùng từ phiếu ĐÓNG GÓI — bắt buộc trừ nguyên liệu."
              : "SP KHÔNG sản xuất — nguyên liệu / hàng mua từ NCC (nhập kho qua phiếu nhập hàng)."}
          </div>
        )}
        {inv.product && isAdmin && inv.product.can_package && hasRecipe === false && (
          <div class="muted small" style={{ margin: "-4px 0 6px", color: "#c0392b" }}>
            ⚠ Chưa khai công thức — khai ở khối Công thức bên dưới mới nhập được phiếu đóng gói.
          </div>
        )}
        {inv.product && isAdmin && (
          <div class="box-kv">
            <span class="box-k">Mua bán</span>
            <div class="row">
              <button class={"trade-chip" + (inv.product.can_sell !== false ? " on" : "")} onClick={() => toggleTrade("can_sell")}>
                <Icon name="tag" size={14} /> {inv.product.can_sell !== false ? "Có thể bán" : "Không bán"}
              </button>
              <button class={"trade-chip" + (inv.product.can_purchase !== false ? " on" : "")} onClick={() => toggleTrade("can_purchase")}>
                <Icon name="truck" size={14} /> {inv.product.can_purchase !== false ? "Có thể nhập" : "Không nhập"}
              </button>
            </div>
          </div>
        )}
        {inv.product && isAdmin && (
          <div class="muted small" style={{ margin: "-2px 0 6px" }}>
            Tắt = SP không hiện trong gợi ý {inv.product.can_sell === false && inv.product.can_purchase === false
              ? "hoá đơn bán lẫn phiếu nhập NCC"
              : inv.product.can_sell === false ? "hoá đơn bán" : inv.product.can_purchase === false ? "phiếu nhập NCC" : "(đang bật cả hai)"}.
          </div>
        )}
        <div class="row space">
          {inv.product?.linked ? (
            <span class="kv-badge on" title={inv.product.kv_full_name || undefined}>
              <Icon name="link" size={16} /> Đã liên kết KiotViet{inv.product.kv_id ? ` #${inv.product.kv_id}` : ""}
            </span>
          ) : (
            <span class="kv-badge off">⚠️ Chưa liên kết KiotViet</span>
          )}
          {isAdmin && (
            <span class="row">
              {inv.product?.linked
                ? <button class="btn small" onClick={doUnlink}>Bỏ liên kết</button>
                : <>
                    <button class="btn small primary" onClick={openLink}><Icon name="link" size={16} /> Liên kết</button>
                    <button class="btn small" disabled={kvCreating} onClick={openKvCreate}><Icon name="plus" size={15} /> Tạo trên KiotViet</button>
                  </>}
              {inv.product && <button class="btn small danger" title="Xoá mã khỏi danh mục" onClick={doDelete}><Icon name="trash" size={16} /></button>}
            </span>
          )}
        </div>
      </section>

      {linkOpen && (
        <div class="modal-overlay" onClick={() => setLinkOpen(false)}>
          <div class="modal-sheet" onClick={(e: any) => e.stopPropagation()}>
            <div class="modal-head"><Icon name="link" size={18} /> Liên kết {code} với KiotViet</div>
            <input class="inv-search" type="search" autofocus placeholder="Tìm SP KiotViet (tên/mã)…"
              value={kvQ} onInput={(e: any) => setKvQ(e.target.value)} />
            {kvLoading ? (
              <p class="muted small"><LoadingInline label="Đang tìm…" /></p>
            ) : kvRes.length === 0 ? (
              <p class="muted small">{kvQ.trim().length < 2 ? "Gõ ≥2 ký tự để tìm." : "Không thấy SP KiotViet."}</p>
            ) : (
              <div class="inv-detail-list kv-list">
                {kvRes.map((kv) => (
                  <button class="inv-detail-row link kv-row" key={kv.id} onClick={() => doLink(kv)}>
                    <code class="inv-bc">{kv.code}</code>
                    <span class="prod-ord-text">{kv.full_name}</span>
                    <span class="muted small">#{kv.id}</span>
                  </button>
                ))}
              </div>
            )}
            <button class="btn block mt-2" onClick={() => setLinkOpen(false)}>Đóng</button>
          </div>
        </div>
      )}

      {kvCatOpen && (
        <div class="modal-overlay" onClick={() => setKvCatOpen(false)}>
          <div class="modal-sheet" onClick={(e: any) => e.stopPropagation()}>
            <div class="modal-head"><Icon name="plus" size={18} /> Tạo {code} trên KiotViet</div>
            <div class="muted small" style={{ marginBottom: "8px" }}>
              Tên: {inv.product?.name || code} · Đơn vị: {inv.product?.unit || "cây"}
            </div>
            <div class="box-kv">
              <span class="box-k">Nhóm hàng</span>
              <SelectPopup title="Chọn nhóm hàng KiotViet" searchable placeholder={kvCats.length ? "Chọn nhóm hàng" : "Đang tải…"}
                value={kvCatId} options={kvCats.map((c) => ({ value: c.id, label: c.name }))}
                onChange={setKvCatId} />
            </div>
            <div class="row mt-2">
              <button class="btn primary fill" disabled={kvCreating || !kvCatId} onClick={doKvCreate}>
                {kvCreating ? <LoadingInline label="Đang tạo…" /> : "Tạo + liên kết"}
              </button>
              <button class="btn" onClick={() => setKvCatOpen(false)}>Huỷ</button>
            </div>
          </div>
        </div>
      )}

      {inv.groups.length > 0 && (
        <div class="inv-groups" style={{ margin: "6px 0 12px" }}>
          {inv.groups.map((g) => (
            <span class="inv-chip" key={g.quantity}>
              {g.count} thùng × {soVN(g.quantity)}
            </span>
          ))}
        </div>
      )}

      <section class="card">
        {(() => {
          const rem = (b: InvBox) => (b.remaining ?? b.quantity ?? 0);
          const stocked = all.filter((b) => rem(b) > 0);
          const emptied = all.filter((b) => rem(b) <= 0);
          const shown = showEmpty ? all : stocked;
          return (
            <>
              <div class="row space">
                <label class="card-label" style={{ margin: 0 }}>Danh sách thùng ({stocked.length}{emptied.length ? ` + ${emptied.length} đã hết` : ""})</label>
                <BoxViewToggle value={invView} onChange={setInvView} />
              </div>
              {all.length === 0 ? (
                <div class="muted small">Chưa có thùng nào.</div>
              ) : shown.length === 0 ? (
                <div class="muted small">Không còn thùng nào có hàng.</div>
              ) : invView === "compact" ? (
                <CompactBoxList boxes={shown as any} flat />
              ) : (() => {
                // Ô thùng GOM THEO VỊ TRÍ KHO (SP chỉ 1 mã → ẩn mã trên ô, ô nhỏ)
                const g = new Map<string, InvBox[]>();
                for (const b of shown) { const k = b.place_name || "Chưa xếp vị trí"; const a = g.get(k); if (a) a.push(b); else g.set(k, [b]); }
                const sumRem = (bs: InvBox[]) => bs.reduce((s, b) => s + Math.max(0, rem(b)), 0);
                const groups = [...g.entries()].sort((a, b) => sumRem(b[1]) - sumRem(a[1]) || a[0].localeCompare(b[0]));
                return (
                  <div class="kho-groups">
                    {groups.map(([pname, bs]) => {
                      const pid = bs.find((x) => x.place_id)?.place_id;
                      return (
                        <section class="kho-group" key={pname}>
                          {pid ? (
                            <a class="kho-group-h" href={`#/vi-tri/${pid}`}>
                              <b>{pname}</b><span class="muted small">{soVN(sumRem(bs))} tồn · {bs.length} thùng →</span>
                            </a>
                          ) : (
                            <div class="kho-group-h"><b>{pname}</b><span class="muted small">{soVN(sumRem(bs))} tồn · {bs.length} thùng</span></div>
                          )}
                          <BoxLabelGrid boxes={bs} dense />
                        </section>
                      );
                    })}
                  </div>
                );
              })()}
              {emptied.length > 0 && (
                <button class="btn small block mt-2" onClick={() => setShowEmpty((v) => !v)}>
                  {showEmpty ? "Ẩn thùng đã hết" : `Hiện ${emptied.length} thùng đã hết`}
                </button>
              )}
            </>
          );
        })()}
      </section>

      <RecipeEditor productCode={code} />

      {inv.product?.id ? <History base={`/api/media/product/${inv.product.id}`} /> : null}

      <section class="card" ref={ordSecRef}>
        <label class="card-label">Đơn có sản phẩm này{ordStarted.current ? ` (${ordTotal})` : ""}</label>
        {!ordStarted.current || (ordLoading && ords.length === 0) ? (
          <div class="muted small"><LoadingInline /></div>
        ) : ords.length === 0 ? (
          <div class="muted small">Chưa có đơn nào chứa mã này.</div>
        ) : (
          <>
            <div class="inv-detail-list">
              {ords.map((o) => (
                <a key={o.thread_id} class="inv-detail-row link" href={`#/order/${o.thread_id}`}>
                  <code class="inv-bc">#{o.thread_id}</code>
                  <span class="prod-ord-text">{o.text || "(trống)"}</span>
                  {o.sl != null && <span class="inv-q">×{soVN(o.sl)}</span>}
                  {o.price != null && o.price > 0 && <span class="muted small">{money(o.price)}</span>}
                </a>
              ))}
            </div>
            {ordMore && (
              <button class="btn small block mt-2" disabled={ordLoading} onClick={() => loadOrders(false)}>
                {ordLoading ? <LoadingInline /> : `Xem thêm (${ordTotal - ords.length})`}
              </button>
            )}
          </>
        )}
      </section>
    </div>
  );
}
