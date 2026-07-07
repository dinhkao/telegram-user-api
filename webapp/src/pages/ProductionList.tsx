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
let prodCache: { slips: ProdSlip[]; page: number; totalPages: number; kind: string } | null = null;
type KindF = "" | "san_xuat" | "dong_goi";

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
  } else if (idx >= 0) {
    const next = prodCache.slips.slice();
    next[idx] = { ...next[idx], ...(e.row as ProdSlip) };
    prodCache = { ...prodCache, slips: next };
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
      const r = await listProduction(page, kindFRef.current || undefined);
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
      setSlips(prodCache.slips);
      st.current.page = prodCache.page;
      st.current.totalPages = prodCache.totalPages;
    } else {
      load(1, false);
    }
    productionCatalog().then(setCatalog).catch(() => {});
  }, []);
  // Lưu snapshot khi rời trang
  const slipsRef = useRef<ProdSlip[]>([]);
  slipsRef.current = slips;
  useEffect(() => () => {
    if (slipsRef.current.length) prodCache = { slips: slipsRef.current, page: st.current.page, totalPages: st.current.totalPages, kind: kindFRef.current };
  }, []);

  const applyFilter = (k: KindF) => {
    if (k === kindFRef.current) return;
    kindFRef.current = k; setKindF(k); prodCache = null;
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
        const matches = !f || ((e.row as ProdSlip).kind || "san_xuat") === f;
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
  const total = slip.total || 0;
  return (
    <a class="prod-card" href={`#/san_xuat/${slip.thread_id}`}>
      <div class="prod-card-top">
        <span class="prod-sp">
          {slip.sp_name || "Chưa có SP"}
          {(slip.kind || "san_xuat") === "dong_goi"
            ? <span class="pk-badge pack"><Icon name="box" size={12} /> Đóng gói</span>
            : <span class="pk-badge sx"><Icon name="factory" size={12} /> Sản xuất</span>}
        </span>
        <span class="prod-date"><Icon name="clock" size={14} /> {(() => { const c = prodCreated(slip); return c.includes(" ") ? c.split(" ")[1] : c; })()}</span>
      </div>
      <div class="prod-card-stat">
        <span class="prod-total"><Icon name="box" size={14} /> {soVN(total)}</span>
        {boxes.length > 0 && <span class="muted small">· {boxes.length} thùng</span>}
      </div>
      {boxes.length > 0 && <BoxMiniGrid boxes={boxes} />}
      {slip.ghi_chu && <div class="prod-card-note"><Icon name="note" size={13} /> {slip.ghi_chu}</div>}
    </a>
  );
}
