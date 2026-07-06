// Dashboard kho — mỗi product 1 card: tồn (in_stock) + số thùng đã xuất/đã giao.
// Tap card → #/kho/:code (chi tiết thùng). GET /api/inventory. Realtime: box mới
// phát production_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import { inventoryList, soVN, type InvProductSummary } from "../api";
import { foldVN } from "../format";
import { onRealtime } from "../realtime";
import { Loading, EmptyState, ErrorState } from "../ui/states";

export function InventoryList() {
  const [products, setProducts] = useState<InvProductSummary[] | null>(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");

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
      <h2 class="page-h">📦 Kho hàng <span class="muted small">({products.length} mã)</span></h2>
      <input class="inv-search" type="search" placeholder="🔎 Tìm mã / tên sản phẩm…" value={q}
        onInput={(e: any) => setQ(e.target.value)} />
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
