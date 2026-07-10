// Cần làm hàng (#/nhu-cau) — BẢNG ĐIỀU PHỐI SẢN XUẤT, thiết kế TRIAGE.
// Đơn tạo hôm nay chưa xuất kho → mã nào thiếu tồn chia 2 vùng quyết định:
//   • CẦN QUYẾT ĐỊNH (thiếu NL / chưa cấu hình) — thẻ mở sẵn, thấy lý do + cách gỡ.
//   • LÀM ĐƯỢC (SX trực tiếp / đóng gói đủ) — thẻ gập, mỗi thẻ 1 dòng "phán": làm gì.
// Mã đủ tồn gộp gọn cuối trang. Data: stockDemand(); triage/BOM tính ở client.
import { useEffect, useState } from "preact/hooks";
import { stockDemand, soVN, type StockDemandResult, type StockDemandLine, type StockDemandIngredient, type StockDemandOrder } from "../api";
import { onRealtime } from "../realtime";
import { BackLink } from "../nav";
import { Icon } from "../ui/Icon";
import { Loading, EmptyState, ErrorState } from "../ui/states";

const enc = encodeURIComponent;
const r3 = (n: number) => Math.round(n * 1000) / 1000;

// ── helpers ─────────────────────────────────────────────────────────────
// 2 trục: SX trực tiếp được không (can_direct) × có công thức NL không (hasRecipe).
function planOf(p: StockDemandLine) {
  const ings = p.ingredients || [];
  const hasRecipe = ings.length > 0;
  const matsEnough = hasRecipe && ings.every((g) => g.enough);
  const canDirect = p.can_direct !== false;
  return { ings, hasRecipe, matsEnough, canDirect };
}
// mức độ (vùng + ưu tiên): blocked=phải làm/mua NL trước; stuck=chưa cấu hình cách SX;
// fallback=đóng gói thiếu NL nhưng làm trực tiếp được; makeable=làm ngay được.
type Sev = "makeable" | "fallback" | "blocked" | "stuck";
function sevOf(p: StockDemandLine): Sev {
  const { hasRecipe, matsEnough, canDirect } = planOf(p);
  if (canDirect) return hasRecipe && !matsEnough ? "fallback" : "makeable";
  if (!hasRecipe) return "stuck";
  return matsEnough ? "makeable" : "blocked";
}
const SEV_PRIO: Record<Sev, number> = { blocked: 0, stuck: 0, fallback: 1, makeable: 2 };
// vùng CẦN QUYẾT ĐỊNH = cần người quyết (mua/làm NL, cấu hình); vùng LÀM ĐƯỢC = cứ làm.
const needsDecision = (p: StockDemandLine) => { const s = sevOf(p); return s === "blocked" || s === "stuck"; };
// so sánh trong 1 vùng: theo mức độ → thiếu nhiều trước → nhiều đơn trước
const cmpLine = (a: StockDemandLine, b: StockDemandLine) =>
  SEV_PRIO[sevOf(a)] - SEV_PRIO[sevOf(b)] || b.shortfall - a.shortfall || b.orders - a.orders;

// Phân tích ĐÓNG GÓI: tồn NL đóng gói được thêm bao nhiêu thành phẩm? (need_i = ratio_i×thiếu
// → NL đủ đóng gói full thiếu ⟺ stock_i≥need_i. packable = thiếu × min(stock_i/need_i)).
// bn = NL nút thắt; leftover = NL dư sau khi đóng gói; shortIngs = NL còn thiếu để đóng đủ.
function packInfo(p: StockDemandLine) {
  const S = p.shortfall;
  const ings = (p.ingredients || []).filter((g) => g.need > 0);
  if (S <= 0 || !ings.length) return null;
  let ratio = Infinity, bn = ings[0];
  for (const g of ings) { const rr = g.stock / g.need; if (rr < ratio) { ratio = rr; bn = g; } }
  const enough = ings.every((g) => g.stock + 1e-9 >= g.need);
  const packable = enough ? S : Math.floor(S * ratio);   // số thành phẩm nguyên (cây) đóng được ngay
  const stillShort = r3(S - packable);
  const leftover = ings.map((g) => ({ code: g.code, unit: g.unit, rem: r3(g.stock - g.need) }));
  // NL còn thiếu (để đóng gói ĐỦ phần thiếu): cần làm thêm ít nhất g.shortfall mỗi NL
  const shortIngs = ings.filter((g) => !g.enough).map((g) => ({ code: g.code, unit: g.unit, need: g.shortfall }));
  return { S, packable, enough, stillShort, bn, leftover, shortIngs };
}

// ĐOẠN PHÂN TÍCH (luôn hiện với SP có công thức NL) — giải thích cụ thể bằng số: NL nút thắt
// còn bao nhiêu → đóng gói được mấy cây → còn thiếu bao nhiêu / dư gì → lối SX trực tiếp thay thế.
function PackAnalysis({ p }: { p: StockDemandLine }) {
  const pi = packInfo(p);
  if (!pi) return null;
  const u = p.unit || "cây";
  return (
    <div class={"nd-calc " + (pi.enough ? "ok" : "bad")}>
      <Icon name="box" size={13} /> Nguyên liệu <b>{pi.bn.code}</b> còn <b>{soVN(pi.bn.stock)}</b>{pi.bn.unit ? ` ${pi.bn.unit}` : ""}
      {pi.enough ? (
        <> — đủ đóng gói <b>{soVN(pi.S)}</b> {u}. Sau đó NL còn: {pi.leftover.map((l, i) => <span key={l.code}>{i ? ", " : ""}{l.code} <b>{soVN(l.rem)}</b>{l.unit ? ` ${l.unit}` : ""}</span>)}.</>
      ) : (
        <>
          {pi.packable > 0 ? <>, chỉ đủ đóng gói <b>{soVN(pi.packable)}</b> {u}.</> : <>.</>}
          {" "}Cần sản xuất thêm ít nhất{" "}
          {pi.shortIngs.map((g, i) => <span key={g.code}>{i ? " + " : ""}<b class="nd-calc-x">{soVN(g.need)}{g.unit ? ` ${g.unit}` : ""} {g.code}</b></span>)}
          {" "}để đóng gói đủ.
          {p.can_direct !== false && <> Hoặc sản xuất thêm <b>{p.code}</b> <b>{soVN(pi.stillShort)}</b> {u} trực tiếp.</>}
        </>
      )}
    </div>
  );
}

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
const anyUrgent = (p: StockDemandLine) => (p.orders_detail || []).some((o) => dueInfo(o.ngay_giao)?.urgent);

// DÒNG PHÁN (chữ ký của trang) — 1 câu "làm gì", luôn hiện. KHÔNG liệt kê từng NL ở đây.
type Verdict = { icon: string; tone: "ok" | "bad" | "warn"; text: string; resolve?: { href: string; label: string } };
function verdictOf(p: StockDemandLine): Verdict {
  const { hasRecipe, matsEnough, canDirect } = planOf(p);
  const u = p.unit || "cây";
  const sf = soVN(p.shortfall);
  const pi = packInfo(p);
  const kho = `#/kho/${enc(p.code)}`;
  if (!canDirect && !hasRecipe)
    return { icon: "ban", tone: "bad", text: "Chưa cấu hình cách SX", resolve: { href: kho, label: "Bật SX trực tiếp" } };
  if (!canDirect && hasRecipe && !matsEnough) {
    const k = pi ? pi.shortIngs.length : 0;
    return { icon: "box", tone: "bad", text: k >= 2 ? `Thiếu ${k} nguyên liệu` : `Thiếu NL ${pi ? pi.bn.code : ""}`, resolve: { href: kho, label: "Xem nguyên liệu" } };
  }
  if (canDirect && hasRecipe && !matsEnough)
    return { icon: "factory", tone: "warn", text: `SX trực tiếp ${sf} ${u} · thay vì đóng gói` };
  if (!canDirect && hasRecipe && matsEnough)
    return { icon: "box", tone: "ok", text: "Đóng gói từ NL — đủ hàng" };
  return { icon: "factory", tone: "ok", text: `Sản xuất trực tiếp ${sf} ${u}` };
}

// Thanh TỒN KHO: full = tổng tồn của SP; mỗi ĐƠN chiếm 1 khúc % theo tồn.
// Đơn vượt tồn (thiếu) → khúc tràn qua vạch tồn, vùng vượt gạch đỏ.
const SB_PAL = ["#4C9AFF", "#57D9A3", "#B37FEB", "#F78C6C", "#00B8D9", "#FFAB00"];
function StockBar({ stock, need, orders, showNum = true, legend = false }: { stock: number; need: number; orders?: StockDemandOrder[]; showNum?: boolean; legend?: boolean }) {
  const scale = Math.max(stock, need, 0.0001);
  const stockPct = Math.min(100, (stock / scale) * 100);
  const over = need > stock + 1e-6;
  const rem = r3(stock - need);
  const segs = orders && orders.length ? orders : (need > 0 ? [{ thread_id: 0, need, label: "" } as StockDemandOrder] : []);
  let acc = 0;
  const items = segs.map((o, i) => {
    const left = (acc / scale) * 100;
    const w = (o.need / scale) * 100;
    acc += o.need;
    return { o, left, w, color: SB_PAL[i % SB_PAL.length] };
  });
  const withId = items.filter((x) => x.o.thread_id);
  return (
    <>
      <div class="sb">
        {items.map(({ o, left, w, color }) => (
          <span class="sb-seg" key={o.thread_id} title={o.label ? `${o.label}: ${soVN(o.need)}` : undefined}
            style={{ left: `${left}%`, width: `${w}%`, background: color }}>
            {w >= 13 && <span class="sb-seg-n">{soVN(o.need)}</span>}
          </span>
        ))}
        {over && <span class="sb-over" style={{ left: `${stockPct}%` }} />}
        {over && <span class="sb-line" style={{ left: `${stockPct}%` }} />}
        {showNum && (
          <span class={"sb-num" + (rem > 0 ? " ok" : rem === 0 ? " zero" : " neg")}>
            {rem > 0 ? <>còn <b>{soVN(rem)}</b></> : rem === 0 ? "hết" : <>thiếu <b>{soVN(-rem)}</b></>}
          </span>
        )}
      </div>
      {legend && withId.length > 0 && (
        <div class="sb-legend">
          {withId.map(({ o, color }) => {
            const due = dueInfo(o.ngay_giao);
            return (
              <a class="sb-lg" href={`#/order/${o.thread_id}`} key={o.thread_id}>
                <span class="sb-lg-dot" style={{ background: color }} />
                <span class="sb-lg-txt">{o.label}</span>
                {due && <span class={"nd-due" + (due.urgent ? " urgent" : "")}>{due.text}</span>}
                <span class="sb-lg-need">cần <b>{soVN(o.need)}</b> ›</span>
              </a>
            );
          })}
        </div>
      )}
    </>
  );
}

// ── cây nguyên liệu (đệ quy, dùng trong phần mở rộng) ───────────────────
function IngTree({ g, depth }: { g: StockDemandIngredient; depth: number }) {
  const hasNeed = g.need > 0;
  return (
    <>
      <a class="nd-ing" href={`#/kho/${enc(g.code)}`} style={{ paddingLeft: `${10 + depth * 16}px` }}>
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

// ── phần mở rộng: "Cách làm" — GỘP 1 khối duy nhất (không lặp math NL) ────
function HowToMake({ p }: { p: StockDemandLine }) {
  const { ings, hasRecipe, matsEnough, canDirect } = planOf(p);
  const mam = mamText(p.shortfall, p.cay_per_mam);
  const u = p.unit || "cây";
  const both = canDirect && hasRecipe;
  // SX trực tiếp thuần (không công thức) → dòng phán đã nói đủ, khỏi lặp lại.
  if (!hasRecipe && canDirect) return null;
  if (!hasRecipe) {   // !canDirect && !hasRecipe = kẹt (chưa cấu hình)
    return (
      <div class="nd-card-how">
        <div class="nd-sub-h">Cách làm</div>
        <div class="nd-mk bad">
          <div class="nd-mk-head"><Icon name="ban" size={15} /> Chưa cấu hình cách SX</div>
          <div class="nd-mk-sub">Bật "SX trực tiếp" hoặc thêm công thức nguyên liệu ở chi tiết SP.</div>
        </div>
      </div>
    );
  }
  return (
    <div class="nd-card-how">
      <div class="nd-sub-h">Cách làm</div>
      {both && <div class="nd-plan-lb">{matsEnough ? "Chọn 1 trong 2 cách:" : "Cách làm:"}</div>}
      {canDirect && (
        <div class={"nd-opt direct" + (both && !matsEnough ? " rec" : "")}>
          <Icon name="factory" size={15} />
          <span class="nd-opt-t"><b>Sản xuất trực tiếp {soVN(p.shortfall)} {u}</b>{mam ? <span class="nd-dim"> · {mam}</span> : null}</span>
          {both && !matsEnough && <span class="nd-opt-rec">nên chọn</span>}
        </div>
      )}
      {both && <div class="nd-plan-or">hoặc</div>}
      {hasRecipe && (
        <div class={"nd-opt pack " + (matsEnough ? "ok" : "bad")}>
          <div class="nd-opt-h">
            <span class="nd-opt-t"><Icon name="box" size={15} /> <b>Đóng gói từ nguyên liệu</b></span>
            <span class={"nd-tag " + (matsEnough ? "ok" : "bad")}>{matsEnough ? "đủ NL" : "thiếu NL"}</span>
          </div>
          {ings.map((g) => <IngTree g={g} depth={0} key={g.code} />)}
        </div>
      )}
    </div>
  );
}

// ── thẻ SP cần làm — Line1 định danh · Line2 thiếu · Line3 dòng phán · mở rộng ─
function ProductCard({ p, i, defaultOpen, openOverride }: { p: StockDemandLine; i: number; defaultOpen: boolean; openOverride?: boolean | null }) {
  const sev = sevOf(p);
  const [open, setOpen] = useState(defaultOpen);
  useEffect(() => { if (openOverride != null) setOpen(openOverride); }, [openOverride]);
  const v = verdictOf(p);
  const mam = mamText(p.shortfall, p.cay_per_mam);
  const u = p.unit || "cây";
  const urgent = anyUrgent(p);
  const hasBar = (p.orders_detail && p.orders_detail.length > 0) || p.need > 0;
  return (
    <article class={"nd-card " + sev} style={{ animationDelay: `${Math.min(i, 8) * 40}ms` }}>
      <button class="nd-card-top" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span class="nd-card-id">
          <span class="nd-card-code">{p.code}</span>
          {p.name ? <span class="nd-card-name">{p.name}</span> : null}
        </span>
        <span class="nd-card-meta">
          {mam && planOf(p).canDirect && <span class="nd-mam">{mam}</span>}
          {urgent && <span class="nd-due urgent"><Icon name="clock" size={11} /> hôm nay</span>}
        </span>
      </button>

      <div class="nd-card-def">
        <b class="nd-sf">thiếu {soVN(p.shortfall)} {u}</b>
        <span class="nd-card-ctx">· tồn {soVN(p.stock)} · cần {soVN(p.need)} · {p.orders} đơn</span>
      </div>

      <div class={"nd-verdict-line " + v.tone}>
        <Icon name={v.icon} size={15} />
        <span class="nd-vl-txt">{v.text}</span>
        {v.resolve && <a class="nd-act" href={v.resolve.href}>{v.resolve.label} ›</a>}
      </div>

      {/* ĐOẠN PHÂN TÍCH — số liệu cụ thể, luôn hiện (chỉ SP có công thức NL) */}
      <PackAnalysis p={p} />

      {open && (
        <div class="nd-card-detail">
          {hasBar && (
            <>
              <div class="nd-sub-h">Tồn kho theo đơn</div>
              <StockBar stock={p.stock} need={p.need} orders={p.orders_detail} showNum={false} legend />
            </>
          )}
          <HowToMake p={p} />
        </div>
      )}

      <button class="nd-card-more" onClick={() => setOpen(!open)}>
        {open ? <>Ẩn bớt <Icon name="chevronDown" size={14} /></> : <>Xem chi tiết <Icon name="chevronRight" size={14} /></>}
      </button>
    </article>
  );
}

// gộp thống kê 1 vùng: số mã + Σ thiếu + đơn vị chung (khác đơn vị → "cây")
function bucketStat(list: StockDemandLine[]) {
  const sum = r3(list.reduce((s, p) => s + p.shortfall, 0));
  const u = list.length && list.every((p) => p.unit === list[0].unit) ? (list[0].unit || "cây") : "cây";
  return { n: list.length, sum, u };
}

// ── trang ───────────────────────────────────────────────────────────────
export function StockDemand() {
  const [data, setData] = useState<StockDemandResult | null>(null);
  const [err, setErr] = useState("");
  const [goAllOpen, setGoAllOpen] = useState<boolean | null>(null);   // "Mở hết / Ẩn hết" vùng LÀM ĐƯỢC
  const [showOk, setShowOk] = useState<boolean | null>(null);          // gập vùng ĐỦ HÀNG (mặc định mở)

  const load = async () => {
    try { setData(await stockDemand()); setErr(""); }
    catch (e: any) { setErr(e?.message || "Lỗi tải Cần làm hàng"); }
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
        <div class="nd-head-title">Cần làm hàng</div>
        <div class="nd-head-sub">Đơn đang chờ, chưa xuất kho</div>
      </div>
    </div>
  );

  if (err) return <div class="nd-page">{head}<ErrorState msg={err} onRetry={load} /></div>;
  if (!data) return <div class="nd-page">{head}<Loading /></div>;

  const { products, totals } = data;
  const noProd = data.no_products || [];
  const warn = noProd.length > 0 ? (
    <div class="nd-warn">
      <div class="nd-warn-h"><span class="nd-warn-i"><Icon name="ban" size={15} /></span> Có <b>{noProd.length}</b> đơn chưa nhập sản phẩm — kết quả có thể KHÔNG chính xác.</div>
      <div class="nd-warn-chips">
        {noProd.map((o) => <a class="nd-warn-chip" href={`#/order/${o.thread_id}`} key={o.thread_id}>{o.label} ›</a>)}
      </div>
    </div>
  ) : null;
  if (products.length === 0) {
    return (
      <div class="nd-page">{head}{warn}
        <EmptyState icon="check">Chưa có đơn nào cần làm hàng.</EmptyState>
      </div>
    );
  }

  const short = products.filter((p) => !p.enough);
  const decide = short.filter(needsDecision).sort(cmpLine);
  const go = short.filter((p) => !needsDecision(p)).sort(cmpLine);
  const okList = products.filter((p) => p.enough);
  const ds = bucketStat(decide), gs = bucketStat(go);

  return (
    <div class="nd-page">
      {head}
      {warn}

      {/* VERDICT — câu phán tổng, không phải bảng số */}
      {short.length === 0 ? (
        <div class="nd-verdict clear">
          <Icon name="check" size={26} />
          <div>
            <div class="nd-v-line">Kho đủ cho mọi đơn đang chờ</div>
            <div class="nd-v-sub">{totals.orders} đơn · {products.length} mã đều có sẵn</div>
          </div>
        </div>
      ) : (
        <div class="nd-verdict alert">
          <div class="nd-v-count">{short.length}</div>
          <div class="nd-v-main">
            <div class="nd-v-line">mã cần làm thêm</div>
            <div class="nd-v-sub">{totals.orders} đơn chưa đủ hàng</div>
            <div class="nd-v-plan">{decide.length > 0 ? <>{decide.length} cần quyết định · {go.length} làm được</> : <>{go.length} mã làm được</>}</div>
            <div class="nd-v-chips">{[...decide, ...go].map((p) => <a class="nd-chip" href={`#/kho/${enc(p.code)}`} key={p.code}>{p.code}</a>)}</div>
          </div>
        </div>
      )}

      {/* VÙNG A — CẦN QUYẾT ĐỊNH (thẻ mở sẵn) */}
      {decide.length > 0 && (
        <section class="nd-sec">
          <div class="nd-sec-h">
            <span class="nd-sec-title decide"><Icon name="ban" size={15} /> CẦN QUYẾT ĐỊNH</span>
            <span class="nd-sec-stat">{ds.n} mã · thiếu {soVN(ds.sum)} {ds.u}</span>
          </div>
          <div class="nd-sec-sub">Phải làm / mua nguyên liệu trước, hoặc cấu hình cách SX</div>
          {decide.map((p, i) => <ProductCard p={p} i={i} defaultOpen key={p.code} />)}
        </section>
      )}

      {/* VÙNG B — LÀM ĐƯỢC (thẻ gập, có "Mở hết / Ẩn hết") */}
      {go.length > 0 && (
        <section class="nd-sec">
          <div class="nd-sec-h">
            <span class="nd-sec-title go"><Icon name="check" size={15} /> LÀM ĐƯỢC</span>
            <span class="nd-sec-right">
              <span class="nd-sec-stat">{gs.n} mã · thiếu {soVN(gs.sum)}</span>
              <button class="nd-sec-toggle" onClick={() => setGoAllOpen((x) => x !== true)}>{goAllOpen ? "Ẩn hết" : "Mở hết"}</button>
            </span>
          </div>
          <div class="nd-sec-sub">Sẵn sàng — SX trực tiếp hoặc đóng gói</div>
          {go.map((p, i) => <ProductCard p={p} i={i} defaultOpen={false} openOverride={goAllOpen} key={p.code} />)}
        </section>
      )}

      {/* ĐỦ HÀNG — vẫn cần thấy TỒN CÒN LẠI SAU ĐƠN để quyết định nhập thêm */}
      {okList.length > 0 && (() => {
        const openOk = showOk === null ? true : showOk;
        return (
          <section class="nd-ok">
            <button class="nd-ok-h" onClick={() => setShowOk(!openOk)}>
              <span><Icon name="check" size={15} /> Đủ hàng · {okList.length} mã</span>
              <span class="nd-ok-toggle">{openOk ? "ẩn" : "xem"} <Icon name={openOk ? "chevronDown" : "chevronRight"} size={14} /></span>
            </button>
            {openOk && (
              <div class="nd-ok-list">
                {okList.map((p) => (
                  <div class="nd-ok-row" key={p.code}>
                    <div class="nd-ok-top">
                      <a class="nd-ok-code" href={`#/kho/${enc(p.code)}`}>{p.code}{p.name ? <span class="nd-dim"> {p.name}</span> : null}</a>
                      <span class="nd-ok-foot">cần {soVN(p.need)}{p.unit ? ` ${p.unit}` : ""} · tồn {soVN(p.stock)}</span>
                    </div>
                    <StockBar stock={p.stock} need={p.need} orders={p.orders_detail} legend />
                  </div>
                ))}
              </div>
            )}
          </section>
        );
      })()}
    </div>
  );
}
