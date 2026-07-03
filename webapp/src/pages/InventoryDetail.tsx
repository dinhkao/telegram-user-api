// Chi tiết kho 1 product — danh sách mọi thùng + tình trạng (Trong kho / Đã xuất
// đơn #x / Đã giao). GET /api/inventory/:code (all_boxes). Nhóm tồn theo size ở đầu.
// Thùng đã xuất link tới đơn. Realtime production_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import { inventoryDetail, soVN, type InvDetail, type InvBox } from "../api";
import { onRealtime } from "../realtime";

const STATUS: Record<string, { label: string; cls: string }> = {
  in_stock: { label: "Trong kho", cls: "in" },
  allocated: { label: "Đã xuất", cls: "alloc" },
  shipped: { label: "Đã giao", cls: "ship" },
};

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
        if (e.type === "resync" || e.type === "production_changed") load();
      }),
    [code]
  );

  if (err) return <div class="error-banner">{err}</div>;
  if (!inv) return <div class="muted">Đang tải…</div>;
  const all: InvBox[] = inv.all_boxes;

  return (
    <div class="inv-detail">
      <div class="prod-detail-head">
        <a class="back" href="#/kho">
          ←
        </a>
        <div>
          <div class="prod-sp big">{inv.product_code}</div>
          <div class="prod-date muted">
            Tồn: {soVN(inv.total)} · {inv.box_count} thùng
          </div>
        </div>
      </div>

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
              const st = STATUS[b.status] || { label: b.status, cls: "" };
              const tail = b.order_thread_id ? ` #${b.order_thread_id}` : "";
              // Tap thùng → trang chi tiết thùng (phiếu nguồn + đơn phân bổ)
              return (
                <a
                  key={b.id}
                  class={b.disabled ? "inv-detail-row link box-off" : "inv-detail-row link"}
                  href={`#/thung/${b.id}`}
                >
                  <code class="inv-bc">{b.box_code}</code>
                  <span class="inv-q">{soVN(b.quantity)}</span>
                  {b.note && <span class="inv-note muted small">📝 {b.note}</span>}
                  {b.disabled ? (
                    <span class="inv-status disabled" title={b.disabled_reason || undefined}>
                      Vô hiệu
                    </span>
                  ) : (
                    <span class={`inv-status ${st.cls}`}>
                      {st.label}
                      {tail}
                    </span>
                  )}
                  <span class="inv-when muted small">{fmtWhen(b.created_at)}</span>
                </a>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
