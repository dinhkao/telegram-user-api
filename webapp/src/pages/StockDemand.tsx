// Nhu cầu kho (#/nhu-cau) — BẢNG ĐIỀU PHỐI SẢN XUẤT. Của các đơn TẠO HÔM NAY chưa
// xuất kho: mã nào KHÔNG đủ tồn → "phiếu cần làm" (thiếu bao nhiêu · ≈ mấy mâm · làm
// được không theo tồn nguyên liệu · đơn nào chờ). Mã đủ → gộp gọn cuối trang.
// Data: stockDemand(); mọi tính toán triage/BOM ở client từ payload sẵn có.
import { useEffect, useState } from "preact/hooks";
import { stockDemand, soVN, type StockDemandResult, type StockDemandLine, type StockDemandIngredient, type StockDemandOrder } from "../api";
import { onRealtime } from "../realtime";
import { BackLink } from "../nav";
import { Icon } from "../ui/Icon";
import { Loading, EmptyState, ErrorState } from "../ui/states";

// ── helpers ─────────────────────────────────────────────────────────────
type MakeState = "none" | "makeable" | "blocked";   // không công thức / đủ NL / thiếu NL

function makeState(p: StockDemandLine): MakeState {
  const ings = p.ingredients || [];
  if (!ings.length) return "none";
  return ings.every((g) => g.enough) ? "makeable" : "blocked";
}
// ưu tiên phiếu: thiếu NL (phải mua) → làm trực tiếp → đủ NL; cùng nhóm thì thiếu nhiều lên trước
const PRIO: Record<MakeState, number> = { blocked: 0, none: 1, makeable: 2 };

function mamText(shortfall: number, cpm?: number): string | null {
  if (!cpm || cpm <= 0) return null;
  return `≈ ${Math.max(1, Math.ceil(shortfall / cpm))} mâm`;   // làm nguyên mâm → làm tròn LÊN
}

// ngay_giao "2026-07-10T00:00" → "hôm nay" / "mai" / "12/07"; + cờ tới hạn
function dueInfo(iso?: string): { text: string; urgent: boolean } | null {
  if (!iso || iso.length < 10) return null;
  const d = iso.slice(0, 10);
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  if (d === today) return { text: "giao hôm nay", urgent: true };
  const t = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  const tomo = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")}`;
  if (d === tomo) return { text: "giao mai", urgent: false };
  return { text: `giao ${d.slice(8, 10)}/${d.slice(5, 7)}`, urgent: d < today };
}

// ── cây nguyên liệu (đệ quy, dùng trong phần mở rộng) ───────────────────
function IngTree({ g, depth }: { g: StockDemandIngredient; depth: number }) {
  const hasNeed = g.need > 0;
  return (
    <>
      <a class="nd-ing" href={`#/kho/${encodeURIComponent(g.code)}`} style={{ paddingLeft: `${10 + depth * 16}px` }}>
        {depth > 0 && <span class="nd-ing-tick">└</span>}
        <span class="nd-ing-body">
          <span class="nd-ing-code"><b>{g.code}</b>{g.name ? <span class="nd-dim"> {g.name}</span> : null}</span>
          <span class="nd-ing-nums">{hasNeed ? <>cần <b>{soVN(g.need)}</b> · </> : null}tồn {soVN(g.stock)}{g.unit ? ` ${g.unit}` : ""}</span>
        </span>
        {hasNeed
          ? <span class={"nd-tag " + (g.enough ? "ok" : "bad")}>{g.enough ? "đủ" : `thiếu ${soVN(g.shortfall)}`}</span>
          : <span class="nd-tag calm">còn hàng</span>}
      </a>
      {(g.children || []).map((c) => <IngTree g={c} depth={depth + 1} key={c.code} />)}
    </>
  );
}

// verdict "làm được không" — dải quyết định của phiếu
function MakeVerdict({ p, state }: { p: StockDemandLine; state: MakeState }) {
  if (state === "none") {
    return <div class="nd-mk none"><Icon name="factory" size={15} /> Làm trực tiếp — không có công thức nguyên liệu</div>;
  }
  const blockers = (p.ingredients || []).filter((g) => !g.enough);
  if (state === "makeable") {
    const names = (p.ingredients || []).map((g) => g.code).join(", ");
    return (
      <div class="nd-mk ok">
        <div class="nd-mk-head"><Icon name="check" size={15} /> Đủ nguyên liệu để làm <b>{soVN(p.shortfall)}</b></div>
        <div class="nd-mk-sub">{names}</div>
      </div>
    );
  }
  return (
    <div class="nd-mk bad">
      <div class="nd-mk-head"><span class="nd-mk-warn">⚠</span> Thiếu nguyên liệu — phải bổ sung</div>
      {blockers.map((g) => (
        <a class="nd-mk-block" href={`#/kho/${encodeURIComponent(g.code)}`} key={g.code}>
          <b>{g.code}</b><span class="nd-dim"> cần {soVN(g.need)} · tồn {soVN(g.stock)}</span>
          <span class="nd-tag bad">thiếu {soVN(g.shortfall)}</span>
        </a>
      ))}
    </div>
  );
}

// đơn đang chờ mã này (phần mở rộng)
function AffectedOrder({ o, unit }: { o: StockDemandOrder; unit: string }) {
  const due = dueInfo(o.ngay_giao);
  return (
    <a class="nd-ord" href={`#/order/${o.thread_id}`}>
      <span class="nd-ord-txt">{o.label}</span>
      <span class="nd-ord-right">
        {due && <span class={"nd-due" + (due.urgent ? " urgent" : "")}>{due.text}</span>}
        <span class="nd-ord-need">{soVN(o.need)}{unit ? ` ${unit}` : ""} ›</span>
      </span>
    </a>
  );
}

// ── phiếu cần làm (mã thiếu hàng) ───────────────────────────────────────
function MakeTicket({ p, i }: { p: StockDemandLine; i: number }) {
  const [open, setOpen] = useState(false);
  const state = makeState(p);
  const det = p.orders_detail || [];
  const cover = p.need > 0 ? Math.max(0, Math.min(100, (p.stock / p.need) * 100)) : 0;
  const mam = mamText(p.shortfall, p.cay_per_mam);
  return (
    <article class={"nd-tk " + state} style={{ animationDelay: `${Math.min(i, 8) * 45}ms` }}>
      <div class="nd-tk-top">
        <div class="nd-tk-id">
          <span class="nd-tk-code">{p.code}</span>
          {p.name ? <span class="nd-tk-name">{p.name}</span> : null}
        </div>
        {mam && <span class="nd-mam">{mam}</span>}
      </div>

      <div class="nd-def">
        <span class="nd-def-lb">thiếu</span>
        <span class="nd-def-num">{soVN(p.shortfall)}</span>
        <span class="nd-def-unit">{p.unit || "cây"}</span>
        <span class="nd-def-ctx">tồn {soVN(p.stock)} · cần {soVN(p.need)} · {p.orders} đơn</span>
      </div>
      <div class="nd-cover"><span class="nd-cover-fill" style={{ width: `${cover}%` }} /></div>

      <MakeVerdict p={p} state={state} />

      <button class="nd-tk-more" onClick={() => setOpen((v) => !v)}>
        <Icon name={open ? "chevronDown" : "chevronRight"} size={15} />
        {open ? "Ẩn chi tiết" : `${p.orders} đơn chờ · nguyên liệu`}
      </button>
      {open && (
        <div class="nd-tk-detail">
          <div class="nd-sub-h">Đơn đang chờ</div>
          {det.map((o) => <AffectedOrder o={o} unit={p.unit} key={o.thread_id} />)}
          {(p.ingredients || []).length > 0 && (
            <>
              <div class="nd-sub-h">Nguyên liệu (đệ quy)</div>
              {(p.ingredients || []).map((g) => <IngTree g={g} depth={0} key={g.code} />)}
            </>
          )}
        </div>
      )}
    </article>
  );
}

// ── trang ───────────────────────────────────────────────────────────────
export function StockDemand() {
  const [data, setData] = useState<StockDemandResult | null>(null);
  const [err, setErr] = useState("");
  const [showOk, setShowOk] = useState(false);

  const load = async () => {
    try { setData(await stockDemand()); setErr(""); }
    catch (e: any) { setErr(e?.message || "Lỗi tải nhu cầu kho"); }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    let t: any;
    const off = onRealtime((e) => {
      if (["resync", "order_changed", "orders_changed", "inventory_changed", "box_changed"].includes(e.type)) {
        clearTimeout(t); t = setTimeout(load, 400);
      }
    });
    return () => { off(); clearTimeout(t); };
  }, []);

  const head = (
    <div class="nd-head">
      <BackLink fallback="#/kho" />
      <div class="nd-head-t">
        <div class="nd-head-title">Nhu cầu hôm nay</div>
        <div class="nd-head-sub">Đơn tạo hôm nay chưa xuất kho</div>
      </div>
    </div>
  );

  if (err) return <div class="nd-page">{head}<ErrorState msg={err} onRetry={load} /></div>;
  if (!data) return <div class="nd-page">{head}<Loading /></div>;

  const { products, totals } = data;
  if (products.length === 0) {
    return (
      <div class="nd-page">{head}
        <EmptyState icon="check">Chưa có đơn mới nào cần hàng hôm nay.</EmptyState>
      </div>
    );
  }

  const short = products.filter((p) => !p.enough).sort((a, b) => PRIO[makeState(a)] - PRIO[makeState(b)] || b.shortfall - a.shortfall);
  const okList = products.filter((p) => p.enough);

  return (
    <div class="nd-page">
      {head}

      {/* VERDICT — câu phán, không phải bảng số */}
      {short.length === 0 ? (
        <div class="nd-verdict clear">
          <Icon name="check" size={26} />
          <div>
            <div class="nd-v-line">Kho đủ cho mọi đơn hôm nay</div>
            <div class="nd-v-sub">{totals.orders} đơn · {products.length} mã đều có sẵn</div>
          </div>
        </div>
      ) : (
        <div class="nd-verdict alert">
          <div class="nd-v-count">{short.length}</div>
          <div class="nd-v-main">
            <div class="nd-v-line">mã cần bổ sung</div>
            <div class="nd-v-sub">{totals.orders} đơn hôm nay chưa đủ hàng</div>
            <div class="nd-v-chips">{short.map((p) => <a class="nd-chip" href={`#/kho/${encodeURIComponent(p.code)}`} key={p.code}>{p.code}</a>)}</div>
          </div>
        </div>
      )}

      {/* PHIẾU CẦN LÀM */}
      {short.length > 0 && (
        <section class="nd-sec">
          <div class="nd-sec-h">Cần làm</div>
          {short.map((p, i) => <MakeTicket p={p} i={i} key={p.code} />)}
        </section>
      )}

      {/* ĐỦ HÀNG — gộp gọn */}
      {okList.length > 0 && (
        <section class="nd-ok">
          <button class="nd-ok-h" onClick={() => setShowOk((v) => !v)}>
            <span><Icon name="check" size={15} /> Đủ hàng · {okList.length} mã</span>
            <span class="nd-ok-toggle">{showOk ? "ẩn" : "xem"} <Icon name={showOk ? "chevronDown" : "chevronRight"} size={14} /></span>
          </button>
          {showOk && (
            <div class="nd-ok-list">
              {okList.map((p) => (
                <a class="nd-ok-row" href={`#/kho/${encodeURIComponent(p.code)}`} key={p.code}>
                  <span class="nd-ok-code">{p.code}</span>
                  <span class="nd-ok-nums">cần {soVN(p.need)} · tồn {soVN(p.stock)}</span>
                  <Icon name="check" size={14} class="nd-ok-ck" />
                </a>
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
