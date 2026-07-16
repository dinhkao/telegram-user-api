// Danh sách phiếu sản xuất — GET /api/production (phân trang 20/trang, cuộn tải
// thêm như dashboard đơn). Card → #/san_xuat/:thread_id. Tạo phiếu mới ở đầu.
// Realtime: productions_changed/resync → tải lại trang 1; production_changed → vá.
import { useEffect, useRef, useState } from "preact/hooks";
import {
  listProduction,
  createProduction,
  productionCatalog,
  soVN,
  prodCreated,
  allBoxes,
  type ProdSlip,
  type ProdCatalogItem,
  type KhoBox,
} from "../api";
import { onRealtime } from "../realtime";
import { ProductPicker } from "../detail/ProductPicker";
import { BoxMiniGrid } from "../detail/BoxMiniGrid";
import { Loading, EmptyState } from "../ui/states";
import { Icon } from "../ui/Icon";

// Cache list đã tải → quay lại giữ nguyên + hệ cuộn khôi phục vị trí (khỏi tải lại).
let prodCache: { slips: ProdSlip[]; page: number; totalPages: number; kind: string; day: string; mm?: boolean } | null = null;
type KindF = "" | "san_xuat" | "dong_goi";

// Lọc "LỆCH NHẬP" — CÙNG RULE server (_mismatch_sql) + badge card: phiếu SX từ
// 10/07/2026 có báo cáo thợ mà tổng nhập thùng lệch tổng báo cáo >1%.
const MM_SINCE = "20260710";
function slipMismatch(s: ProdSlip): boolean {
  if ((s.kind || "san_xuat") === "dong_goi") return false;
  if (slipDayCode(s) < MM_SINCE) return false;
  if (s.report_total === undefined) return true;   // row realtime thiếu số liệu → giữ, reload sau chỉnh
  const rep = s.report_total || 0;
  if (rep <= 0) return false;
  return Math.abs((s.boxed_total ?? 0) - rep) > rep * 0.01;
}

// Mã ngày 'YYYYMMDD' của 1 phiếu (từ date_code lúc tạo; fallback date "DD/MM/YYYY").
function slipDayCode(s: ProdSlip): string {
  if (s.date_code && s.date_code.length >= 8) return s.date_code.slice(0, 8);
  const p = (s.date || "").split(" ")[0].split("/");
  return p.length === 3 ? p[2] + p[1].padStart(2, "0") + p[0].padStart(2, "0") : "";
}
const dayToCode = (d: string) => d.replace(/-/g, "");   // "YYYY-MM-DD" → "YYYYMMDD"

// Lưu bộ lọc (kind + ngày) vào localStorage → NHỚ qua cả reload / mở lại app.
const PROD_FILTER_KEY = "prod_filter_v1";
function loadFilter(): { kind: KindF; day: string; mm: boolean } {
  try { const j = JSON.parse(localStorage.getItem(PROD_FILTER_KEY) || "{}"); return { kind: (j.kind || "") as KindF, day: j.day || "", mm: !!j.mm }; }
  catch { return { kind: "", day: "", mm: false }; }
}
function saveFilter(kind: KindF, day: string, mm = false) {
  try { localStorage.setItem(PROD_FILTER_KEY, JSON.stringify({ kind, day, mm })); } catch { /* im */ }
}
const dayVN = (d: string) => { const [, m, dd] = d.split("-"); return dd && m ? `${dd}/${m}` : d; };   // nhãn ngắn

// FIX realtime khi trang ĐANG UNMOUNT (ở trang khác): handler trong component chết nên
// bỏ lỡ event → quay lại thấy cache cũ. Subscriber cấp-module này LUÔN sống, VÁ prodCache
// tại chỗ (giữ vị trí cuộn, KHÔNG co về trang 1). Chỉ bỏ cache khi thêm/xoá phiếu (cấu
// trúc list đổi) hoặc reconnect.
onRealtime((e) => {
  if (e.type === "productions_changed" || e.type === "resync") { prodCache = null; return; }
  if (e.type !== "production_changed" || !prodCache) return;
  const idx = prodCache.slips.findIndex((s) => String(s.thread_id) === e.thread_id);
  if (e.row === null) {
    if (idx >= 0) prodCache = { ...prodCache, slips: prodCache.slips.filter((_, i) => i !== idx) };
    return;
  }
  // Tôn trọng bộ lọc kind của cache (như listener in-page): đổi loại rời khỏi lọc → gỡ;
  // phiếu chưa có trong cache mà khớp lọc → CHÈN đầu (vd: tạo phiếu rồi bật 'đóng gói'
  // ở trang detail — event tới khi list unmount, thiếu nhánh chèn là quay lại dashboard
  // không thấy phiếu, phải reload).
  const row = e.row as ProdSlip;
  const matches = (!prodCache.kind || (row.kind || "san_xuat") === prodCache.kind)
    && (!prodCache.day || slipDayCode(row) === dayToCode(prodCache.day))
    && (!prodCache.mm || slipMismatch(row));
  if (idx >= 0) {
    prodCache = matches
      ? { ...prodCache, slips: prodCache.slips.map((s, i) => (i === idx ? { ...s, ...row } : s)) }
      : { ...prodCache, slips: prodCache.slips.filter((_, i) => i !== idx) };
  } else if (matches) {
    prodCache = { ...prodCache, slips: [row, ...prodCache.slips] };
  }
});

export function ProductionList() {
  const [slips, setSlips] = useState<ProdSlip[]>([]);
  const [catalog, setCatalog] = useState<ProdCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newCode, setNewCode] = useState("");
  const [err, setErr] = useState("");
  const [total, setTotal] = useState(0);
  const [kindF, setKindF] = useState<KindF>("");   // lọc loại phiếu
  const kindFRef = useRef<KindF>("");
  const [dayF, setDayF] = useState("");            // lọc 1 ngày ("YYYY-MM-DD"), "" = mọi ngày
  const dayFRef = useRef("");
  const [mmF, setMmF] = useState(false);           // lọc phiếu SX LỆCH NHẬP (từ 10/07/2026)
  const mmFRef = useRef(false);
  const st = useRef({ page: 1, totalPages: 1, loading: false });
  const sentinel = useRef<HTMLDivElement>(null);
  // Thùng theo phiếu (source_thread_id) — 1 lần gọi allBoxes, gom nhóm
  const [boxesByThread, setBoxesByThread] = useState<Record<number, KhoBox[]>>({});
  const loadBoxes = async () => {
    try {
      const all = await allBoxes();
      const g: Record<number, KhoBox[]> = {};
      for (const b of all) if (b.source_thread_id != null) (g[b.source_thread_id] ||= []).push(b);
      for (const k in g) g[k].sort((a, b) => a.box_code.localeCompare(b.box_code));
      setBoxesByThread(g);
    } catch { /* im */ }
  };
  useEffect(() => {
    loadBoxes();
    return onRealtime((e) => {
      if (e.type === "box_changed" || e.type === "inventory_changed" || e.type === "production_changed" || e.type === "resync") loadBoxes();
    });
  }, []);

  const load = async (page: number, append: boolean) => {
    if (st.current.loading) return;
    st.current.loading = true;
    if (!append) setLoading(true);
    try {
      const r = await listProduction(page, kindFRef.current || undefined, dayFRef.current ? dayToCode(dayFRef.current) : undefined, mmFRef.current);
      st.current.page = r.page;
      st.current.totalPages = r.total_pages;
      setTotal(r.total);
      setSlips((prev) => (append ? [...prev, ...r.slips] : r.slips));
    } catch (e: any) {
      setErr(e?.message || "Lỗi tải danh sách");
    } finally {
      st.current.loading = false;
      setLoading(false);
    }
  };

  useEffect(() => {
    if (prodCache) {   // quay lại → dựng lại list đã tải (giữ đúng bộ lọc đã xem)
      kindFRef.current = prodCache.kind as KindF; setKindF(prodCache.kind as KindF);
      dayFRef.current = prodCache.day || ""; setDayF(prodCache.day || "");
      mmFRef.current = !!prodCache.mm; setMmF(!!prodCache.mm);
      setSlips(prodCache.slips);
      st.current.page = prodCache.page;
      st.current.totalPages = prodCache.totalPages;
    } else {
      const f = loadFilter();   // nhớ bộ lọc qua reload / mở lại app
      kindFRef.current = f.kind; setKindF(f.kind);
      dayFRef.current = f.day; setDayF(f.day);
      mmFRef.current = f.mm; setMmF(f.mm);
      load(1, false);
    }
    productionCatalog().then(setCatalog).catch(() => {});
  }, []);
  // Lưu snapshot khi rời trang
  const slipsRef = useRef<ProdSlip[]>([]);
  slipsRef.current = slips;
  useEffect(() => () => {
    if (slipsRef.current.length) prodCache = { slips: slipsRef.current, page: st.current.page, totalPages: st.current.totalPages, kind: kindFRef.current, day: dayFRef.current, mm: mmFRef.current };
  }, []);

  const applyFilter = (k: KindF) => {
    if (k === kindFRef.current) return;
    kindFRef.current = k; setKindF(k); prodCache = null;
    saveFilter(k, dayFRef.current, mmFRef.current);
    setSlips([]); st.current.page = 1; st.current.totalPages = 1;
    load(1, false);
  };
  const applyDayFilter = (day: string) => {
    if (day === dayFRef.current) return;
    dayFRef.current = day; setDayF(day); prodCache = null;
    saveFilter(kindFRef.current, day, mmFRef.current);
    setSlips([]); st.current.page = 1; st.current.totalPages = 1;
    load(1, false);
  };
  const applyMmFilter = () => {
    const v = !mmFRef.current;
    mmFRef.current = v; setMmF(v); prodCache = null;
    saveFilter(kindFRef.current, dayFRef.current, v);
    setSlips([]); st.current.page = 1; st.current.totalPages = 1;
    load(1, false);
  };

  // Realtime
  useEffect(() => {
    return onRealtime((e) => {
      if (e.type === "productions_changed" || e.type === "resync") {
        load(1, false);
        return;
      }
      if (e.type !== "production_changed") return;
      const tid = e.thread_id;
      setSlips((prev) => {
        const idx = prev.findIndex((s) => String(s.thread_id) === tid);
        if (e.row === null) return idx >= 0 ? prev.filter((_, i) => i !== idx) : prev;
        // tôn trọng bộ lọc: phiếu đổi loại rời khỏi lọc → gỡ; loại khác thêm mới → bỏ qua
        const f = kindFRef.current;
        const dayOk = !dayFRef.current || slipDayCode(e.row as ProdSlip) === dayToCode(dayFRef.current);
        const mmOk = !mmFRef.current || slipMismatch(e.row as ProdSlip);
        const matches = (!f || ((e.row as ProdSlip).kind || "san_xuat") === f) && dayOk && mmOk;
        if (idx >= 0) {
          if (!matches) return prev.filter((_, i) => i !== idx);
          const next = prev.slice();
          next[idx] = { ...next[idx], ...(e.row as ProdSlip) };
          return next;
        }
        return matches ? [e.row as ProdSlip, ...prev] : prev;
      });
    });
  }, []);

  // Cuộn tải thêm (như OrdersList)
  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries[0].isIntersecting) return;
        const { page, totalPages, loading: ld } = st.current;
        if (ld || page >= totalPages) return;
        load(page + 1, true);
      },
      { rootMargin: "300px" }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const doCreate = async () => {
    setCreating(true);
    setErr("");
    try {
      const tid = await createProduction(newCode || undefined);
      window.location.hash = `#/san_xuat/${tid}`;
    } catch (e: any) {
      setErr(e?.message || "Tạo phiếu thất bại");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div class="prod-list">
      <div class="prod-create">
        <ProductPicker catalog={catalog} value={newCode} onPick={setNewCode} placeholder="Tìm mã SP (tuỳ chọn)" />
        <button class="btn primary" disabled={creating} onClick={doCreate}>
          {creating ? "Đang tạo…" : <><Icon name="plus" size={16} /> Tạo phiếu</>}
        </button>
      </div>

      <div class="prod-filter">
        <button class={"pf-chip" + (kindF === "" ? " on" : "")} onClick={() => applyFilter("")}>Tất cả</button>
        <button class={"pf-chip" + (kindF === "san_xuat" ? " on" : "")} onClick={() => applyFilter("san_xuat")}><Icon name="factory" size={14} /> Sản xuất</button>
        <button class={"pf-chip" + (kindF === "dong_goi" ? " on" : "")} onClick={() => applyFilter("dong_goi")}><Icon name="box" size={14} /> Đóng gói</button>
        <button class={"pf-chip pf-mm" + (mmF ? " on" : "")} onClick={applyMmFilter}
          title="Phiếu SX (từ 10/07/2026) có báo cáo thợ lệch tổng nhập thùng >1%">⚠ Lệch nhập</button>
        <label class={"pf-chip pf-day" + (dayF ? " on" : "")} title="Lọc phiếu theo ngày tạo">
          <Icon name="calendar" size={14} />
          <span class="pf-day-lb">{dayF ? dayVN(dayF) : "Ngày"}</span>
          <input type="date" value={dayF}
            onClick={(e: any) => { try { e.currentTarget.showPicker?.(); } catch { /* im */ } }}
            onInput={(e: any) => applyDayFilter(e.target.value)} />
        </label>
        {dayF && <button class="pf-chip pf-clear" onClick={() => applyDayFilter("")} title="Bỏ lọc ngày"><Icon name="close" size={13} /></button>}
      </div>

      {err && <div class="error-banner">{err}</div>}
      {loading && !slips.length && <Loading />}
      {!loading && !slips.length && <EmptyState>Chưa có phiếu sản xuất nào.</EmptyState>}

      <div class="prod-cards">
        {groupByDay(slips).map((g) => (
          <div class="prod-group" key={g.key}>
            <div class="prod-group-head">{g.label} <span class="muted small">({g.slips.length})</span></div>
            {g.slips.map((s) => <ProdCard key={s.thread_id} slip={s} boxes={boxesByThread[s.thread_id] || []} />)}
          </div>
        ))}
      </div>

      <div ref={sentinel} style={{ height: "1px" }} />
      {slips.length > 0 && (
        <div class="muted small" style={{ textAlign: "center", padding: "10px" }}>
          {slips.length}/{total} phiếu
        </div>
      )}
    </div>
  );
}

const _WD = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];

/** Nhóm phiếu theo NGÀY tạo (slip đã sắp mới→cũ). Trả [{key, label, slips}]. */
function groupByDay(slips: ProdSlip[]): { key: string; label: string; slips: ProdSlip[] }[] {
  const out: { key: string; label: string; slips: ProdSlip[] }[] = [];
  for (const s of slips) {
    const key = (prodCreated(s).split(" ")[0]) || "?";   // "DD/MM/YYYY"
    const last = out[out.length - 1];
    if (last && last.key === key) last.slips.push(s);
    else out.push({ key, label: dayLabel(key), slips: [s] });
  }
  return out;
}

function dayLabel(key: string): string {
  const [d, m, y] = key.split("/").map(Number);
  if (!d || !m || !y) return "Không rõ ngày";
  const date = new Date(y, m - 1, d);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const diff = Math.round((today.getTime() - date.getTime()) / 86400000);
  const wd = _WD[date.getDay()];
  const dm = `${key.slice(0, 5)}`; // DD/MM
  if (diff === 0) return `Hôm nay · ${wd} ${dm}`;
  if (diff === 1) return `Hôm qua · ${wd} ${dm}`;
  return `${wd} · ${key}`;
}

function ProdCard({ slip, boxes }: { slip: ProdSlip; boxes: KhoBox[] }) {
  // Tổng NHẬP THÙNG = Σ quantity thùng tạo từ phiếu (UI web) — KHÔNG tính số nhập tay
  const total = slip.boxed_total ?? 0;
  const isSX = (slip.kind || "san_xuat") !== "dong_goi";
  const workers = (isSX && slip.report_workers) || [];
  // Khớp/lệch nhập thùng vs báo cáo — CÙNG RULE panel so sánh trang chi tiết (lệch ≤1% = khớp)
  const repTotal = slip.report_total || 0;
  const pctOff = repTotal > 0 ? (Math.abs(total - repTotal) / repTotal) * 100 : total === 0 ? 0 : 100;
  const cmpCls = workers.length > 0 ? (pctOff <= 1 ? " ok" : " warn") : "";
  // Phiếu ĐÓNG GÓI: "<người> đóng gói <N SP> từ nguyên liệu <NL…>" — TÁCH theo từng SP
  const packItems = (!isSX && (slip.pack_items || []).length > 0) ? slip.pack_items! : null;
  return (
    <a class="prod-card" href={`#/san_xuat/${slip.thread_id}`}>
      <div class="prod-card-top">
        <span class="prod-sp">
          {slip.sp_name || (slip.boxed_codes && slip.boxed_codes.length ? slip.boxed_codes.join(", ") : "Chưa có SP")}
          {isSX
            ? <span class="pk-badge sx"><Icon name="factory" size={12} /> Sản xuất</span>
            : <span class="pk-badge pack"><Icon name="box" size={12} /> Đóng gói</span>}
        </span>
        <span class="prod-date"><Icon name="clock" size={14} /> {(() => { const c = prodCreated(slip); return c.includes(" ") ? c.split(" ")[1] : c; })()}</span>
      </div>
      {packItems && (
        <div class="prod-pack-line">
          <Icon name="box" size={12} />{" "}
          {slip.pack_by && <span>{slip.pack_by} đóng gói </span>}
          {!slip.pack_by && <span>Đóng gói </span>}
          {packItems.map((it, i) => (
            <span key={it.product}>
              {i > 0 && <span class="pp-sep"> · </span>}
              <b>{soVN(it.qty)} {it.unit ? it.unit + " " : ""}{it.product}</b>
              {it.materials.length > 0 && <> từ nguyên liệu <b>{it.materials.map((m) => `${soVN(m.amount)} ${m.unit ? m.unit + " " : ""}${m.code}`).join(", ")}</b></>}
            </span>
          ))}
        </div>
      )}
      <div class={"prod-card-body" + (workers.length > 0 ? " with-chart" : "")}>
        {workers.length > 0 && (
          <div class="pcb-chart">
            <div class={"pcb-head right" + cmpCls}><Icon name="users" size={12} /> {soVN(repTotal)}</div>
            <WorkerMiniChart workers={workers} notes={isSX ? slip.report_notes || [] : []} />
          </div>
        )}
        {(workers.length > 0 || boxes.length > 0 || total > 0) && (
          <div class="prod-card-boxes">
            <div class={"pcb-head" + cmpCls}>{soVN(total)} <Icon name="box" size={12} /></div>
            {boxes.length > 0
              ? <BoxMiniGrid boxes={boxes} />
              : <div class="pcb-empty">Chưa nhận sản phẩm</div>}
          </div>
        )}
      </div>
      {slip.ghi_chu && <div class="prod-card-note"><Icon name="note" size={13} /> {slip.ghi_chu}</div>}
    </a>
  );
}

/** Mini chart báo cáo thợ: thanh NGANG (tên | thanh + số trong thanh), ghi chú thợ 0 sản
 * lượng đứng CẠNH chart — cả cụm chỉ chiếm 50% bề ngang card. */
function WorkerMiniChart({ workers, notes }: {
  workers: { name: string; tong: number }[];
  notes: { name: string; note: string }[];
}) {
  const max = Math.max(...workers.map((w) => w.tong), 1);
  return (
    <div class="prod-mini-chart">
      <div class="pmc-chart">
        {workers.map((w) => (
          <div class="pmc-row" key={w.name}>
            <span class="pmc-name">{w.name}</span>
            <span class="pmc-track">
              <span class="pmc-bar" style={{ width: `${Math.max(12, Math.round((w.tong / max) * 100))}%` }}>
                <span class="pmc-val">{soVN(w.tong)}</span>
              </span>
            </span>
          </div>
        ))}
      </div>
      {notes.length > 0 && (
        <div class="pmc-notes">
          {notes.map((n) => (
            <div class="pmc-note" key={n.name}>{n.name} {n.note}</div>
          ))}
        </div>
      )}
    </div>
  );
}
