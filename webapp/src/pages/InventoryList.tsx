// Dashboard kho — mỗi product 1 card: tồn (in_stock) + số thùng đã xuất/đã giao.
// Tap card → #/kho/:code (chi tiết thùng). GET /api/inventory. Realtime: box mới
// phát production_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import { inventoryList, soVN, type InvProductSummary } from "../api";
import { onRealtime } from "../realtime";

export function InventoryList() {
  const [products, setProducts] = useState<InvProductSummary[] | null>(null);
  const [err, setErr] = useState("");

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
        if (e.type === "resync" || e.type === "production_changed") load();
      }),
    []
  );

  if (err) return <div class="error-banner">{err}</div>;
  if (!products) return <div class="muted">Đang tải…</div>;

  return (
    <div class="inv-dash">
      <h2 class="page-h">📦 Kho hàng</h2>
      {!products.length && (
        <div class="muted center" style={{ padding: "40px 0" }}>
          Kho trống. Nhập thùng ở phiếu SX (🏭 SX).
        </div>
      )}
      {products.map((p) => (
        <a class="inv-card" href={`#/kho/${encodeURIComponent(p.product_code)}`} key={p.product_code}>
          <div class="inv-card-code">{p.product_code}</div>
          <div class="inv-card-stat">
            <span class="inv-card-total">{soVN(p.in_stock_total)}</span>
            <span class="muted small">tồn · {p.in_stock_count} thùng</span>
          </div>
          <div class="inv-card-tags">
            {p.allocated_count > 0 && <span class="inv-tag alloc">Đã xuất {p.allocated_count}</span>}
            {p.shipped_count > 0 && <span class="inv-tag ship">Đã giao {p.shipped_count}</span>}
          </div>
        </a>
      ))}
    </div>
  );
}
