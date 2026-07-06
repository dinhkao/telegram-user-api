// Dashboard kho — mỗi product 1 card: tồn (in_stock) + số thùng đã xuất/đã giao.
// Tap card → #/kho/:code (chi tiết thùng). GET /api/inventory. Realtime: box mới
// phát production_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import { inventoryList, createProduct, soVN, type InvProductSummary } from "../api";
import { foldVN } from "../format";
import { onRealtime } from "../realtime";
import { toast } from "../ui/feedback";
import { useScrollLock } from "../useScrollLock";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { Icon } from "../ui/Icon";

export function InventoryList() {
  const [products, setProducts] = useState<InvProductSummary[] | null>(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [nCode, setNCode] = useState("");
  const [nName, setNName] = useState("");
  const [creating, setCreating] = useState(false);
  useScrollLock(createOpen);

  const doCreate = async () => {
    const code = nCode.trim().toUpperCase();
    if (!code) return;
    setCreating(true);
    try {
      const r = await createProduct(code, nName.trim());
      toast(r.existed ? `Mã ${code} đã có` : `✅ Tạo mã ${code}`, "ok");
      setCreateOpen(false); setNCode(""); setNName("");
      window.location.hash = `#/kho/${encodeURIComponent(code)}`;
    } catch (e: any) {
      toast(e?.message || "Tạo lỗi", "err");
    } finally {
      setCreating(false);
    }
  };

  const load = async () => {
    try {
      setProducts(await inventoryList());
    } catch (e: any) {
      setErr(e?.message || "Lỗi tải kho");
    }
  };
  useEffect(() => {
    load();
  }, []);
  useEffect(
    () =>
      onRealtime((e) => {
        if (e.type === "resync" || e.type === "production_changed" || e.type === "inventory_changed" || e.type === "box_changed" || e.type === "order_changed") load();
      }),
    []
  );

  if (err) return <ErrorState msg={err} onRetry={load} />;
  if (!products) return <Loading />;

  const nq = foldVN(q.trim());
  const shown = nq
    ? products.filter((p) => foldVN(p.product_code).includes(nq) || foldVN(p.name || "").includes(nq))
    : products;

  return (
    <div class="inv-dash">
      <div class="row space">
        <h2 class="page-h"><Icon name="box" size={18} /> Kho hàng <span class="muted small">({products.length} mã)</span></h2>
        <button class="btn small primary" onClick={() => setCreateOpen(true)}><Icon name="plus" size={16} /> Tạo mã</button>
      </div>
      <input class="inv-search" type="search" placeholder="Tìm mã / tên sản phẩm…" value={q}
        onInput={(e: any) => setQ(e.target.value)} />

      {createOpen && (
        <div class="modal-overlay" onClick={() => setCreateOpen(false)}>
          <div class="modal-sheet" onClick={(e: any) => e.stopPropagation()}>
            <div class="modal-head"><Icon name="plus" size={18} /> Tạo mã sản phẩm</div>
            <input class="inv-search" autofocus placeholder="Mã SP (vd K2L)" value={nCode}
              onInput={(e: any) => setNCode(e.target.value)} onKeyDown={(e: any) => { if (e.key === "Enter") doCreate(); }} />
            <input class="inv-search" placeholder="Tên (tuỳ chọn)" value={nName}
              onInput={(e: any) => setNName(e.target.value)} onKeyDown={(e: any) => { if (e.key === "Enter") doCreate(); }} />
            <div class="row" style={{ gap: "8px", marginTop: "8px" }}>
              <button class="btn primary" style={{ flex: 1 }} disabled={creating || !nCode.trim()} onClick={doCreate}>
                {creating ? "⏳…" : "Tạo"}
              </button>
              <button class="btn" onClick={() => setCreateOpen(false)}>Huỷ</button>
            </div>
          </div>
        </div>
      )}
      {!products.length ? (
        <EmptyState>Kho trống. Nhập thùng ở phiếu SX (🏭 SX).</EmptyState>
      ) : !shown.length ? (
        <EmptyState>Không có mã khớp.</EmptyState>
      ) : (
        shown.map((p) => (
          <a class="inv-card" href={`#/kho/${encodeURIComponent(p.product_code)}`} key={p.product_code}>
            <div class="inv-card-main">
              <div class="inv-card-code">{p.product_code}{p.linked === false && <span class="inv-unlinked" title="Chưa liên kết KiotViet"> ⚠️</span>}</div>
              {p.name && <div class="inv-card-name muted small">{p.name}</div>}
            </div>
            <div class="inv-card-stat">
              <span class={"inv-card-total" + (p.in_stock_total > 0 ? "" : " zero")}>{soVN(p.in_stock_total)}</span>
              <span class="muted small">tồn · {p.in_stock_count} thùng</span>
            </div>
            <div class="inv-card-tags">
              {p.allocated_count > 0 && <span class="inv-tag alloc">Đã xuất {p.allocated_count}</span>}
              {p.shipped_count > 0 && <span class="inv-tag ship">Đã giao {p.shipped_count}</span>}
            </div>
          </a>
        ))
      )}
    </div>
  );
}
