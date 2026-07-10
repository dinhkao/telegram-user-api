// Nhu cầu kho hôm nay vs tồn (#/nhu-cau). Tổng hàng các đơn TẠO HÔM NAY chưa xuất
// kho còn cần, đối chiếu tồn hiện tại → đủ / thiếu theo từng SP. Data: stockDemand().
import { useEffect, useState } from "preact/hooks";
import { stockDemand, soVN, type StockDemandResult } from "../api";
import { onRealtime } from "../realtime";
import { BackLink } from "../nav";
import { Icon } from "../ui/Icon";
import { Loading, EmptyState, ErrorState } from "../ui/states";

export function StockDemand() {
  const [data, setData] = useState<StockDemandResult | null>(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState<Set<string>>(new Set());
  const toggle = (code: string) => setOpen((s) => { const n = new Set(s); n.has(code) ? n.delete(code) : n.add(code); return n; });

  const load = async () => {
    try { setData(await stockDemand()); setErr(""); }
    catch (e: any) { setErr(e?.message || "Lỗi tải nhu cầu kho"); }
  };
  useEffect(() => { load(); }, []);
  // Đơn mới / xuất kho / tồn đổi → tính lại
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (["resync", "order_changed", "orders_changed", "inventory_changed", "box_changed"].includes(e.type)) {
        clearTimeout(t); t = setTimeout(load, 400);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, []);

  if (err) return <ErrorState msg={err} onRetry={load} />;
  if (!data) return <Loading />;
  const { products, totals } = data;

  return (
    <div class="inv-dash">
      <div class="prod-detail-head">
        <BackLink fallback="#/kho" />
        <div style={{ flex: 1 }}>
          <div class="prod-sp big"><Icon name="box" size={18} /> Nhu cầu kho hôm nay</div>
          <div class="prod-date muted">Đơn tạo hôm nay chưa xuất kho · {totals.orders} đơn</div>
        </div>
      </div>

      {products.length === 0 ? (
        <EmptyState icon="check">Chưa có đơn mới nào cần phân bổ hôm nay.</EmptyState>
      ) : (
        <>
          <div class={"sd-banner " + (totals.all_enough ? "ok" : "short")}>
            {totals.all_enough ? <Icon name="check" size={20} /> : <span class="sd-warn">⚠️</span>}
            {totals.all_enough ? (
              <span>Kho <b>ĐỦ</b> hàng cho {totals.orders} đơn hôm nay ({totals.product_lines} mã).</span>
            ) : (
              <span><b>Thiếu {totals.short_products}</b> / {totals.product_lines} mã · cần thêm tổng <b>{soVN(totals.total_shortfall)}</b>.</span>
            )}
          </div>

          <div class="sd-list">
            {products.map((p) => {
              const pct = p.need > 0 ? Math.max(0, Math.min(100, (p.stock / p.need) * 100)) : 100;
              const det = p.orders_detail || [];
              const isOpen = open.has(p.code);
              return (
                <div class={"sd-item " + (p.enough ? "ok" : "short")} key={p.code}>
                  <button class={"sd-row " + (p.enough ? "ok" : "short")} onClick={() => toggle(p.code)}
                    style={{ "--sd-fill": `${pct}%` } as any}>
                    <Icon name={isOpen ? "chevronDown" : "chevronRight"} size={16} class="sd-chev" />
                    <div class="sd-main">
                      <div class="sd-code"><b>{p.code}</b>{p.name ? <span class="muted small"> · {p.name}</span> : null}</div>
                      <div class="sd-nums">
                        cần <b>{soVN(p.need)}</b>{p.unit ? ` ${p.unit}` : ""} · tồn <b>{soVN(p.stock)}</b>
                        <span class="muted small"> · {p.orders} đơn</span>
                      </div>
                    </div>
                    <div class={"sd-badge " + (p.enough ? "ok" : "short")}>
                      {p.enough ? "đủ" : `thiếu ${soVN(p.shortfall)}`}
                    </div>
                  </button>
                  {isOpen && (
                    <div class="sd-orders">
                      {det.map((o) => (
                        <a class="sd-ord" href={`#/order/${o.thread_id}`} key={o.thread_id}>
                          <span class="sd-ord-lbl">{o.label}</span>
                          <span class="sd-ord-need">cần {soVN(o.need)}{p.unit ? ` ${p.unit}` : ""} →</span>
                        </a>
                      ))}
                      <a class="sd-ord sd-ord-sp" href={`#/kho/${encodeURIComponent(p.code)}`}>
                        <span class="sd-ord-lbl muted">Chi tiết SP {p.code}</span>
                        <span class="sd-ord-need muted">→</span>
                      </a>
                      {p.ingredients && p.ingredients.length > 0 && (
                        <div class="sd-ings">
                          <div class="sd-ings-h">🧪 Nguyên liệu để bù thiếu {soVN(p.shortfall)}{p.unit ? ` ${p.unit}` : ""}</div>
                          {p.ingredients.map((g) => (
                            <a class="sd-ing" href={`#/kho/${encodeURIComponent(g.code)}`} key={g.code}>
                              <span class="sd-ing-main">
                                <span class="sd-ing-code"><b>{g.code}</b>{g.name ? <span class="muted small"> · {g.name}</span> : null}</span>
                                <span class="sd-ing-nums">cần <b>{soVN(g.need)}</b>{g.unit ? ` ${g.unit}` : ""} · tồn {soVN(g.stock)}</span>
                              </span>
                              <span class={"sd-badge " + (g.enough ? "ok" : "short")}>{g.enough ? "đủ" : `thiếu ${soVN(g.shortfall)}`}</span>
                            </a>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
