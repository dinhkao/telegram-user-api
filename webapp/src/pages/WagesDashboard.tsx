// Tiền công thợ theo ngày (#/tien-cong) — NHẠY CẢM (lương), CHỈ văn phòng.
// Server chặn 403 nếu không phải văn phòng; client cũng ẩn nav + trang. Mỗi ngày →
// các thợ (tiền + số cây), bấm thợ mở chi tiết theo SP (số cây × đơn giá = tiền).
// tiền = Σ (số cây SP × lương/SP) từ báo cáo SX. Data: wagesDashboard().
import { useEffect, useState } from "preact/hooks";
import { wagesDashboard, isOffice, soVN, type WagesDashboard as WD } from "../api";
import { onRealtime } from "../realtime";
import { BackLink } from "../nav";
import { Icon } from "../ui/Icon";
import { Loading, EmptyState, ErrorState } from "../ui/states";

const dmy = (ymd: string) => (ymd && ymd.length >= 10 ? `${ymd.slice(8, 10)}/${ymd.slice(5, 7)}` : ymd);
const money = (n: number) => soVN(Math.round(n)) + "đ";

export function WagesDashboard() {
  const [d, setD] = useState<WD | null>(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState<Set<string>>(new Set());   // "ymd|worker" đang mở

  const load = async () => {
    try { setD(await wagesDashboard()); setErr(""); }
    catch (e: any) { setErr(e?.message || "Lỗi tải tiền công"); }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "resync" || e.type === "production_changed" || e.type === "productions_changed") { clearTimeout(t); t = setTimeout(load, 500); }
    });
    return () => { off(); clearTimeout(t); };
  }, []);

  const head = (
    <div class="wg-head">
      <BackLink fallback="#/san_xuat" />
      <div>
        <div class="wg-title"><Icon name="wallet" size={18} /> Tiền công thợ</div>
        <div class="muted small">{d ? `${dmy(d.from)} – ${dmy(d.to)}` : "theo từng ngày"}</div>
      </div>
    </div>
  );

  // Chặn phía client (server đã chặn 403) — không phải văn phòng thì không hiện số liệu.
  if (!isOffice()) return <div class="wg-page">{head}<EmptyState icon="lock">Chỉ văn phòng được xem tiền công.</EmptyState></div>;
  if (err) return <div class="wg-page">{head}<ErrorState msg={err} onRetry={load} /></div>;
  if (!d) return <div class="wg-page">{head}<Loading /></div>;

  const toggle = (k: string) => setOpen((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });

  return (
    <div class="wg-page">
      {head}

      <div class="wg-total">
        <div class="wg-total-money">{money(d.totals.money)}</div>
        <div class="muted small">tổng {d.days.length} ngày · {soVN(d.totals.cay)} cây{(d.totals.allowance || 0) > 0 ? ` · gồm phụ cấp ${money(d.totals.allowance || 0)}` : ""}</div>
      </div>

      {d.missing_wage.length > 0 && (
        <div class="wg-warn">
          <Icon name="ban" size={15} /> Chưa có đơn giá lương cho: {d.missing_wage.map((c, i) => <span key={c}>{i ? ", " : ""}<b>{c}</b></span>)} — số cây các mã này KHÔNG được tính tiền. <a href="#/luong-sp">Cài đơn giá →</a>
        </div>
      )}
      {(d.missing_hour_rate || []).length > 0 && (
        <div class="wg-warn">
          <Icon name="ban" size={15} /> Thợ có GIỜ LÀM nhưng chưa đặt tiền 1 giờ: {d.missing_hour_rate.map((n, i) => (
            <span key={n}>{i ? ", " : ""}<a href={`#/sx-tho/${encodeURIComponent(n)}`}><b>{n}</b></a></span>
          ))} — giờ của họ KHÔNG được tính tiền. Đặt ở trang chi tiết thợ.
        </div>
      )}

      {d.days.length === 0 ? (
        <EmptyState icon="check">Chưa có báo cáo sản xuất nào trong khoảng này.</EmptyState>
      ) : (
        d.days.map((day) => (
          <section class="wg-day" key={day.ymd}>
            <div class="wg-day-h">
              <span class="wg-day-date">{dmy(day.ymd)}</span>
              <span class="wg-day-money">{money(day.money)}</span>
            </div>
            <div class="wg-workers">
              {day.workers.map((w) => {
                const k = day.ymd + "|" + w.name;
                const isOpen = open.has(k);
                return (
                  <div class="wg-wk" key={k}>
                    <button class="wg-wk-row" onClick={() => toggle(k)} aria-expanded={isOpen}>
                      <Icon name={isOpen ? "chevronDown" : "chevronRight"} size={14} />
                      <span class="wg-wk-name">{w.name}</span>
                      {(w.allowance || 0) > 0 ? <span class="wg-wk-pc">+PC {money(w.allowance || 0)}</span> : null}
                      <span class="wg-wk-cay muted small">{soVN(w.cay)} cây</span>
                      <span class="wg-wk-money">{money(w.money)}</span>
                    </button>
                    {isOpen && (
                      <div class="wg-items">
                        {w.items.map((it, i) => (
                          <div class="wg-item" key={i}>
                            <span class="wg-item-code">{it.code}</span>
                            <span class="wg-item-calc muted small">
                              {((it as any).gio || 0) > 0
                                ? <>{soVN((it as any).gio)} giờ × {soVN((it as any).hourly_rate || 0)}đ{((it as any).hourly_rate || 0) <= 0 ? " ⚠ chưa đặt tiền giờ" : ""}</>
                                : <>{soVN(it.cay)} cây × {soVN(it.wage)}đ</>}
                              {(it.allowance || 0) > 0 ? <span class="wg-item-pc-inline"> · +PC {money(it.allowance || 0)}</span> : null}
                            </span>
                            <span class="wg-item-money">{money(it.money)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
