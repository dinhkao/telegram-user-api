// Chi tiết kho 1 product — danh sách mọi thùng + tình trạng (Trong kho / Đã xuất
// đơn #x / Đã giao). GET /api/inventory/:code (all_boxes). Nhóm tồn theo size ở đầu.
// Thùng đã xuất link tới đơn. Realtime production_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import { BackLink } from "../nav";
import { inventoryDetail, syncKiotvietProducts, currentUser, soVN, type InvDetail, type InvBox } from "../api";
import { money } from "../format";
import { onRealtime } from "../realtime";
import { toast } from "../ui/feedback";
import { Loading, ErrorState } from "../ui/states";

function fmtWhen(iso?: string): string {
  if (!iso) return "";
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (!m) return "";
  const [, , mo, d, hh, mi] = m;
  return `${d}/${mo} ${hh}:${mi}`;
}

export function InventoryDetail({ code }: { code: string }) {
  const [inv, setInv] = useState<InvDetail | null>(null);
  const [err, setErr] = useState("");
  const [syncing, setSyncing] = useState(false);
  const isAdmin = currentUser()?.role === "admin";

  const doSync = async () => {
    setSyncing(true);
    try {
      const r = await syncKiotvietProducts();
      toast(`✅ Đồng bộ KiotViet: ${r.synced}/${r.fetched} SP`, "ok");
      await load();
    } catch (e: any) {
      toast(e?.message || "Đồng bộ lỗi", "err");
    } finally {
      setSyncing(false);
    }
  };

  const load = async () => {
    try {
      setInv(await inventoryDetail(code));
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
        if (e.type === "resync" || e.type === "production_changed" || e.type === "inventory_changed" || e.type === "box_changed" || e.type === "order_changed") load();
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

      {/* Tên danh mục + liên kết KiotViet */}
      <section class="card prod-link">
        {inv.product?.name && <div class="prod-link-name">{inv.product.name}</div>}
        <div class="row space">
          {inv.product?.linked ? (
            <span class="kv-badge on" title={inv.product.kv_synced_at ? `Đồng bộ: ${fmtWhen(inv.product.kv_synced_at)}` : undefined}>
              🔗 Đã liên kết KiotViet{inv.product.kv_id ? ` #${inv.product.kv_id}` : ""}
            </span>
          ) : (
            <span class="kv-badge off">⚠️ Chưa liên kết KiotViet</span>
          )}
          {isAdmin && (
            <button class="btn small" disabled={syncing} onClick={doSync}>
              {syncing ? "⏳ Đang đồng bộ…" : "🔄 Đồng bộ"}
            </button>
          )}
        </div>
      </section>

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
        <label class="card-label">Danh sách thùng ({all.length})</label>
        {all.length === 0 ? (
          <div class="muted small">Chưa có thùng nào.</div>
        ) : (
          <div class="inv-detail-list">
            {all.map((b) => {
              const rem = b.remaining ?? b.quantity;
              const used = b.allocated ?? 0;
              // Tap thùng → trang chi tiết thùng (phiếu nguồn + đơn phân bổ)
              return (
                <a
                  key={b.id}
                  class={b.disabled ? "inv-detail-row link box-off" : "inv-detail-row link"}
                  href={`#/thung/${b.id}`}
                >
                  <code class="inv-bc">{b.box_code}</code>
                  <span class="inv-q">
                    {soVN(rem)}
                    {used > 0 ? <span class="muted">/{soVN(b.quantity)}</span> : ""}
                  </span>
                  {b.note && <span class="inv-note muted small">📝 {b.note}</span>}
                  {b.disabled ? (
                    <span class="inv-status disabled" title={b.disabled_reason || undefined}>
                      Vô hiệu
                    </span>
                  ) : used > 0 ? (
                    <span class="inv-status alloc">đã xuất {soVN(used)}</span>
                  ) : (
                    <span class="inv-status in">Trong kho</span>
                  )}
                  <span class="inv-when muted small">{fmtWhen(b.created_at)}</span>
                </a>
              );
            })}
          </div>
        )}
      </section>

      <section class="card">
        <label class="card-label">Đơn có sản phẩm này ({inv.orders.length})</label>
        {inv.orders.length === 0 ? (
          <div class="muted small">Chưa có đơn nào chứa mã này.</div>
        ) : (
          <div class="inv-detail-list">
            {inv.orders.map((o) => (
              <a key={o.thread_id} class="inv-detail-row link" href={`#/order/${o.thread_id}`}>
                <code class="inv-bc">#{o.thread_id}</code>
                <span class="prod-ord-text">{o.text || "(trống)"}</span>
                {o.sl != null && <span class="inv-q">×{soVN(o.sl)}</span>}
                {o.price != null && o.price > 0 && <span class="muted small">{money(o.price)}đ</span>}
              </a>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
