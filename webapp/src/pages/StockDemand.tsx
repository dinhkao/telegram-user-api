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
// 2 trục: SX trực tiếp được không (can_direct) × có công thức NL không (hasRecipe).
function planOf(p: StockDemandLine) {
  const ings = p.ingredients || [];
  const hasRecipe = ings.length > 0;
  const matsEnough = hasRecipe && ings.every((g) => g.enough);
  const canDirect = p.can_direct !== false;
  return { ings, hasRecipe, matsEnough, canDirect };
}
// mức độ (rail + ưu tiên): blocked=phải mua NL, không lối khác; fallback=đóng gói thiếu NL
// nhưng làm trực tiếp được; makeable=làm ngay được; stuck=chưa cấu hình cách SX.
type Sev = "makeable" | "fallback" | "blocked" | "stuck";
function sevOf(p: StockDemandLine): Sev {
  const { hasRecipe, matsEnough, canDirect } = planOf(p);
  if (canDirect) return hasRecipe && !matsEnough ? "fallback" : "makeable";
  if (!hasRecipe) return "stuck";
  return matsEnough ? "makeable" : "blocked";
}
const SEV_PRIO: Record<Sev, number> = { blocked: 0, stuck: 0, fallback: 1, makeable: 2 };

// Phân tích ĐÓNG GÓI: tồn NL đóng gói được thêm bao nhiêu thành phẩm? (need_i = ratio_i×thiếu
// → NL đủ đóng gói full thiếu ⟺ stock_i≥need_i. packable = thiếu × min(stock_i/need_i)).
function packInfo(p: StockDemandLine) {
  const S = p.shortfall;
  const ings = (p.ingredients || []).filter((g) => g.need > 0);
  if (S <= 0 || !ings.length) return null;
  let ratio = Infinity, bn = ings[0];
  for (const g of ings) { const r = g.stock / g.need; if (r < ratio) { ratio = r; bn = g; } }
  const enough = ings.every((g) => g.stock + 1e-9 >= g.need);
  const packable = enough ? S : Math.floor(S * ratio);   // số thành phẩm nguyên (cây)
  const stillShort = Math.round((S - packable) * 1000) / 1000;
  const leftover = ings.map((g) => ({ code: g.code, unit: g.unit, rem: Math.round((g.stock - g.need) * 1000) / 1000 }));
  // NL còn thiếu (để đóng gói ĐỦ phần thiếu): cần làm thêm ít nhất g.shortfall mỗi NL
  const shortIngs = ings.filter((g) => !g.enough).map((g) => ({ code: g.code, unit: g.unit, need: g.shortfall }));
  return { S, packable, enough, stillShort, bn, leftover, shortIngs };
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

// Thanh TỒN KHO: full = tổng tồn của SP; mỗi ĐƠN chiếm 1 khúc % theo tồn.
// Đơn vượt tồn (thiếu) → khúc tràn qua vạch tồn, vùng vượt gạch đỏ.
const SB_PAL = ["#4C9AFF", "#57D9A3", "#B37FEB", "#F78C6C", "#00B8D9", "#FFAB00"];
function StockBar({ stock, need, orders, showNum = true, legend = false }: { stock: number; need: number; orders?: StockDemandOrder[]; showNum?: boolean; legend?: boolean }) {
  const scale = Math.max(stock, need, 0.0001);
  const stockPct = Math.min(100, (stock / scale) * 100);
  const over = need > stock + 1e-6;
  const rem = Math.round((stock - need) * 1000) / 1000;
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

// Cách làm bù phần thiếu — có thể là 2 lựa chọn (SX trực tiếp / đóng gói từ NL).
function MakeVerdict({ p }: { p: StockDemandLine }) {
  const { ings, hasRecipe, matsEnough, canDirect } = planOf(p);
  const mam = mamText(p.shortfall, p.cay_per_mam);
  const u = p.unit || "cây";
  const both = canDirect && hasRecipe;
  if (!canDirect && !hasRecipe) {
    return <div class="nd-mk bad"><div class="nd-mk-head"><span class="nd-mk-warn">⚠</span> Chưa cấu hình cách SX — bật "SX trực tiếp" hoặc thêm công thức NL ở chi tiết SP</div></div>;
  }
  return (
    <div class="nd-plan">
      {both && <div class="nd-plan-lb">{matsEnough ? "Chọn 1 trong 2 cách:" : "Cách làm:"}</div>}
      {canDirect && (
        <div class={"nd-opt direct" + (both && !matsEnough ? " rec" : "")}>
          <Icon name="factory" size={15} />
          <span class="nd-opt-t"><b>Cần sản xuất trực tiếp {soVN(p.shortfall)} {u}</b>{mam ? <span class="nd-dim"> · {mam}</span> : null}</span>
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

// ── phiếu cần làm (mã thiếu hàng) — MỌI chi tiết luôn hiện, không ẩn ─────
function MakeTicket({ p, i }: { p: StockDemandLine; i: number }) {
  const sev = sevOf(p);
  const det = p.orders_detail || [];
  const mam = mamText(p.shortfall, p.cay_per_mam);
  return (
    <article class={"nd-tk " + sev} style={{ animationDelay: `${Math.min(i, 8) * 45}ms` }}>
      <div class="nd-tk-top">
        <div class="nd-tk-id">
          <span class="nd-tk-code">{p.code}</span>
          {p.name ? <span class="nd-tk-name">{p.name}</span> : null}
        </div>
        {mam && planOf(p).canDirect && <span class="nd-mam">{mam}</span>}
      </div>

      <div class="nd-def">
        <span class="nd-def-lb">thiếu</span>
        <span class="nd-def-num">{soVN(p.shortfall)}</span>
        <span class="nd-def-unit">{p.unit || "cây"}</span>
        <span class="nd-def-ctx">tồn {soVN(p.stock)} · cần {soVN(p.need)} · {p.orders} đơn</span>
      </div>
      {(() => {
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
      })()}
      <StockBar stock={p.stock} need={p.need} orders={det} showNum={false} legend />

      <MakeVerdict p={p} />
    </article>
  );
}

// ── trang ───────────────────────────────────────────────────────────────
export function StockDemand() {
  const [data, setData] = useState<StockDemandResult | null>(null);
  const [err, setErr] = useState("");
  const [showOk, setShowOk] = useState<boolean | null>(null);   // null = theo mặc định (bung khi không có phiếu thiếu)

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
      <div class="nd-warn-h"><span class="nd-warn-i">⚠️</span> Có <b>{noProd.length}</b> đơn chưa nhập sản phẩm — kết quả có thể KHÔNG chính xác.</div>
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

  const short = products.filter((p) => !p.enough).sort((a, b) => SEV_PRIO[sevOf(a)] - SEV_PRIO[sevOf(b)] || b.shortfall - a.shortfall);
  const okList = products.filter((p) => p.enough);

  return (
    <div class="nd-page">
      {head}
      {warn}

      {/* VERDICT — câu phán, không phải bảng số */}
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

      {/* ĐỦ HÀNG — vẫn cần thấy TỒN CÒN LẠI SAU ĐƠN để quyết định nhập thêm */}
      {okList.length > 0 && (() => {
        const openOk = showOk === null ? true : showOk;   // luôn hiện chi tiết, đừng ẩn (vẫn cho gập tay)
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
                      <a class="nd-ok-code" href={`#/kho/${encodeURIComponent(p.code)}`}>{p.code}{p.name ? <span class="nd-dim"> {p.name}</span> : null}</a>
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
