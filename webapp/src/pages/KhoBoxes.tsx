// Dashboard KHO HÀNG (#/kho). MẶC ĐỊNH: mỗi VỊ TRÍ kho = 1 card (thumbnail ảnh mới
// nhất + mã SP kèm số lượng tồn tại vị trí đó) → tap mở chi tiết kho. KHI GÕ SEARCH:
// đổi sang lưới Ô THÙNG vuông, GOM THEO VỊ TRÍ. Data + cache module: ./khoData
// (vẽ ngay từ cache khi quay lại, refresh nền). Realtime: KHO_EVENTS → refresh
// debounce 350ms, response cũ không ghi đè mới (seq guard trong khoLoad).
import { useEffect, useMemo, useState } from "preact/hooks";
import { mediaImageUrl, soVN, type Place, type KhoBox } from "../api";
import { khoCache, khoLoad, KHO_EVENTS, type KhoData } from "./khoData";
import { foldVN } from "../format";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { SearchBar } from "../ui/SearchBar";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { BoxLabelGrid } from "../detail/BoxLabelGrid";
import { CompactBoxList } from "../detail/CompactBoxList";

let memQ = "";                 // nhớ search khi rời trang
let memBoxView: "grid" | "compact" = "compact";   // kiểu xem ô thùng ở search (mặc định GỌN)
const MAX_LINES = 6;           // số dòng SP hiện trên 1 card (còn lại gộp "+k")

// Tồn dùng được của 1 thùng (vô hiệu = 0)
const rem = (b: KhoBox) => (b.disabled ? 0 : Math.max(0, b.remaining ?? b.quantity ?? 0));
// Sắp ô thùng: còn dùng được lên trước, rồi mới tạo trước
const usable = (b: KhoBox) => (!b.disabled && (b.remaining ?? b.quantity) > 0 ? 1 : 0);
// Trang kho: ẩn thùng ĐÃ HẾT (còn ≤ 0). Thùng đã hết chỉ xem ở chi tiết SP.
const hasStock = (b: KhoBox) => (b.remaining ?? b.quantity ?? 0) > 0;
const sortBoxes = (a: KhoBox, b: KhoBox) =>
  usable(b) - usable(a) ||
  (b.created_at || "").localeCompare(a.created_at || "") ||
  a.box_code.localeCompare(b.box_code);

// Gộp mã SP + tổng tồn trong 1 nhóm thùng (tồn giảm dần)
function prodAgg(bs: KhoBox[]): { code: string; qty: number }[] {
  const m = new Map<string, number>();
  for (const b of bs) {
    const r = rem(b);
    if (r <= 0) continue;
    m.set(b.product_code, (m.get(b.product_code) || 0) + r);
  }
  return Array.from(m.entries())
    .map(([code, qty]) => ({ code, qty }))
    .sort((a, b) => b.qty - a.qty || a.code.localeCompare(b.code));
}

function ProdChips({ prods }: { prods: { code: string; qty: number }[] }) {
  if (!prods.length) return <div class="kho-loc-empty">Trống — chưa có hàng</div>;
  const head = prods.slice(0, MAX_LINES);
  const more = prods.length - head.length;
  return (
    <div class="kho-loc-prods">
      {head.map((p) => (
        <div class="kho-loc-pline" key={p.code}>
          <span class="kho-loc-pcode">{p.code}</span>
          <span class="kho-loc-pqty">{soVN(p.qty)}</span>
        </div>
      ))}
      {more > 0 && <div class="kho-loc-pmore">+{more} mã khác</div>}
    </div>
  );
}

// Card 1 vị trí kho: thumbnail ảnh mới nhất + mã SP·SL tồn. Tap → chi tiết kho.
function LocCard({ p, bs }: { p: Place; bs: KhoBox[] }) {
  const total = bs.reduce((s, b) => s + rem(b), 0);
  const nStock = bs.filter(hasStock).length;   // đếm CHỈ thùng còn hàng (thùng rỗng đã ẩn)
  return (
    <a class="kho-loc-card" href={`#/vi-tri/${p.id}`}>
      {p.thumb_image_id != null ? (
        <img class="kho-loc-thumb" loading="lazy" alt=""
          src={mediaImageUrl(`/api/media/place/${p.id}`, p.thumb_image_id, "thumb")} />
      ) : (
        <div class="kho-loc-thumb ph"><Icon name="box" size={26} /></div>
      )}
      <div class="kho-loc-main">
        <div class="kho-loc-name">{p.name}</div>
        <div class="kho-loc-meta"><b>{nStock}</b> thùng · <b class={total > 0 ? "kho-loc-t" : ""}>{soVN(total)}</b> tồn</div>
        <ProdChips prods={prodAgg(bs)} />
      </div>
      <Icon name="chevronRight" size={18} class="kg-arrow" />
    </a>
  );
}

export function KhoBoxes() {
  // Vẽ NGAY từ cache module nếu có (không spinner khi quay lại trang).
  const [data, setData] = useState<KhoData | null>(khoCache().data);
  const [err, setErr] = useState("");
  const [q, setQ] = useState(memQ);
  const [boxView, setBoxView] = useState<"grid" | "compact">(memBoxView);
  useEffect(() => { memBoxView = boxView; }, [boxView]);
  useEffect(() => { memQ = q; }, [q]);

  // Cold load (chưa có cache): lỗi → ErrorState. Refresh nền: lỗi → GIỮ cache im lặng.
  const load = async (cold = false) => {
    try {
      const d = await khoLoad();
      if (d) setData(d);   // null = đã có lượt tải mới hơn (bỏ, chống quay ngược)
    } catch (e: any) {
      if (cold || !khoCache().data) setErr(e?.message || "Lỗi tải kho");
    }
  };
  useEffect(() => {
    const c = khoCache();
    if (!c.data) load(true);        // lần đầu: cold load như cũ
    else if (c.dirty) load();       // kho đổi lúc trang đóng: vẽ cache + refresh nền 1 lượt
  }, []);
  // Realtime khi ĐANG MỞ: debounce 350ms — burst nhiều event chỉ tạo 1 batch 3 request.
  useEffect(() => {
    let t: ReturnType<typeof setTimeout> | null = null;
    const off = onRealtime((e) => {
      if (!KHO_EVENTS.has(e.type)) return;
      if (t) clearTimeout(t);
      t = setTimeout(() => { t = null; load(); }, 350);
    });
    return () => { if (t) clearTimeout(t); off(); };
  }, []);

  // Map dựng 1 lần theo data — thay các vòng filter() lặp cho từng vị trí/SP.
  const maps = useMemo(() => {
    const boxes = data?.boxes || [];
    const byPlace = new Map<number, KhoBox[]>();
    const byCode = new Map<string, KhoBox[]>();
    const unplaced: KhoBox[] = [];
    for (const b of boxes) {
      if (b.place_id) {
        const l = byPlace.get(b.place_id); l ? l.push(b) : byPlace.set(b.place_id, [b]);
      } else unplaced.push(b);
      const c = byCode.get(b.product_code); c ? c.push(b) : byCode.set(b.product_code, [b]);
    }
    const stockCountByPlace = new Map<number, number>();
    byPlace.forEach((l, pid) => stockCountByPlace.set(pid, l.filter(hasStock).length));
    const sumByCode = new Map((data?.prodSum || []).map((s) => [s.product_code, s]));
    return { byPlace, byCode, unplaced, stockCountByPlace, sumByCode };
  }, [data]);

  if (err && !data) return <ErrorState msg={err} onRetry={() => { setErr(""); load(true); }} />;
  if (!data) return <Loading />;
  const { places, boxes, prodSum } = data;
  const { byPlace, byCode, unplaced, stockCountByPlace, sumByCode } = maps;

  const nq = foldVN(q.trim());
  const searching = nq !== "";
  // Sắp kho theo NHIỀU THÙNG (còn hàng) nhất lên trước
  const boxCountAt = (pid: number) => stockCountByPlace.get(pid) || 0;
  const sortedPlaces = places.slice().sort((a, b) => boxCountAt(b.id) - boxCountAt(a.id) || a.name.localeCompare(b.name));
  // code → tên SP + tổng tồn kho (search khớp cả TÊN SP + hiện mã SP khớp)
  const fname = (code: string) => foldVN(sumByCode.get(code)?.name || "");
  // Khớp: mã/tên SP (matchName) · ô thùng (thêm số gọi) · TÊN VỊ TRÍ (matchPlaceName)
  const matchName = (b: KhoBox) => foldVN(b.product_code).includes(nq) || fname(b.product_code).includes(nq);
  const matchBox = (b: KhoBox) => matchName(b) || foldVN(b.box_code).includes(nq);
  const matchPlaceName = (p: Place) => foldVN(p.name).includes(nq);
  const matchedPlaces = searching ? sortedPlaces.filter(matchPlaceName) : [];
  const matchedPlaceIds = new Set(matchedPlaces.map((p) => p.id));
  const countBoxes = boxes.filter((b) => hasStock(b) && (matchBox(b) || (b.place_id != null && matchedPlaceIds.has(b.place_id)))).length;

  const header = (
    <div class="row space">
      <h2 class="page-h"><Icon name="box" size={18} /> Kho hàng{" "}
        <span class="muted small">({searching ? `${countBoxes} thùng` : `${places.length} vị trí`})</span>
      </h2>
      <span class="row" style={{ gap: "6px" }}>
        <a class="btn small" href="#/nhu-cau"><Icon name="chart" size={15} /> Cần làm</a>
        <a class="btn small" href="#/san-pham"><Icon name="tag" size={15} /> Sản phẩm</a>
        <a class="btn small" href="#/so-thung"><Icon name="grid" size={15} /> Số thùng</a>
        <a class="btn small" href="#/chuyen-kho"><Icon name="truck" size={15} /> Chuyển kho</a>
      </span>
    </div>
  );
  const search = <SearchBar value={q} onInput={setQ} placeholder="Tìm mã SP / số thùng / vị trí…" />;

  // ── SEARCH: mã SP khớp + VỊ TRÍ khớp (card) + lưới ô thùng gom theo vị trí ─
  if (searching) {
    // Mã SP khớp (theo mã/tên) — dựng từ DANH MỤC (prodSum) nên SP TỒN 0 (chưa có
    // thùng nào) VẪN hiện; tồn giảm dần. Kèm phân bổ theo CỠ: "3 thùng 50 · 2 thùng 30"
    // (gộp thùng còn hàng theo số tồn mỗi thùng; Σ count×tồn = tổng tồn).
    const sizeText = (code: string): string => {
      const bs = (byCode.get(code) || []).filter(hasStock);
      // SP tự-là-thùng (đơn vị SP = 'thùng', mỗi thùng 1 đơn vị): chỉ nói TỔNG số thùng
      if (bs.length && bs.every((b) => (b.product_unit || "") === "thùng")) return `${bs.length} thùng`;
      const m = new Map<number, number>();
      for (const b of bs) { const q = rem(b); m.set(q, (m.get(q) || 0) + 1); }
      return [...m.entries()].sort((a, b) => b[0] - a[0]).map(([q, c]) => `${c} thùng ${soVN(q)}`).join(" · ");
    };
    const spHits = prodSum
      .filter((s) => foldVN(s.product_code).includes(nq) || foldVN(s.name || "").includes(nq))
      .map((s) => ({ code: s.product_code, name: s.name || "", unit: s.unit || "", total: s.in_stock_total || 0, sizes: sizeText(s.product_code) }))
      .sort((a, b) => b.total - a.total || a.code.localeCompare(b.code));

    // Ô thùng khớp mã/tên/số gọi, gom theo vị trí — BỎ vị trí đã hiện dạng CARD
    const groups: { key: string; name: string; href?: string; list: KhoBox[] }[] = [];
    for (const p of sortedPlaces) {
      if (matchedPlaceIds.has(p.id)) continue;
      const list = (byPlace.get(p.id) || []).filter((b) => matchBox(b) && hasStock(b)).sort(sortBoxes);
      if (list.length) groups.push({ key: `p${p.id}`, name: p.name, href: `#/vi-tri/${p.id}`, list });
    }
    const un = unplaced.filter((b) => matchBox(b) && hasStock(b)).sort(sortBoxes);
    if (un.length) groups.push({ key: "none", name: "Chưa xếp vị trí", list: un });

    const nothing = spHits.length === 0 && matchedPlaces.length === 0 && groups.length === 0;

    return (
      <div class="inv-dash">
        {header}{search}
        {spHits.length > 0 && (
          <div class="kho-sp-hits">
            {spHits.map((s) => (
              <a class="kho-sp-hit" href={`#/kho/${encodeURIComponent(s.code)}`} key={s.code}>
                <span class="kho-sp-hit-l">
                  <span class="kho-sp-hit-code">
                    <b>{s.code}</b>
                    <button class="kho-filt-btn" title={`Chỉ lọc mã ${s.code}`}
                      onClick={(e: any) => { e.preventDefault(); e.stopPropagation(); setQ(s.code); }}>
                      <Icon name="filter" size={14} />
                    </button>
                  </span>
                  {s.name ? <span class="muted small">{s.name}</span> : null}
                  {s.sizes ? <span class="kho-sp-sizes">{s.sizes}</span> : null}
                </span>
                <span class={"kho-sp-hit-tot" + (s.total > 0 ? "" : " zero")}>
                  {soVN(s.total)}<span class="muted small"> {s.unit || ""} tồn →</span>
                </span>
              </a>
            ))}
          </div>
        )}
        {matchedPlaces.length > 0 && (
          <div class="kho-loc-list">
            <div class="kho-sec-lbl muted small">Vị trí khớp</div>
            {matchedPlaces.map((p) => (
              <LocCard key={p.id} p={p} bs={byPlace.get(p.id) || []} />
            ))}
          </div>
        )}
        {nothing ? (
          <EmptyState>Không có gì khớp “{q.trim()}”.</EmptyState>
        ) : groups.length > 0 ? (
          <>
            <div class="row" style={{ justifyContent: "flex-end", gap: "6px", marginBottom: "4px" }}>
              <button class={"chip" + (boxView === "grid" ? " active" : "")} onClick={() => setBoxView("grid")}>Ô thùng</button>
              <button class={"chip" + (boxView === "compact" ? " active" : "")} onClick={() => setBoxView("compact")}>Gọn</button>
            </div>
            <div class="kho-groups">
              {groups.map((g) => {
                const tot = g.list.reduce((s, x) => s + rem(x), 0);
                const meta = `${g.list.length} thùng · ${soVN(tot)} tồn`;
                return (
                  <section class={"kho-group" + (boxView === "compact" ? " compact" : "")} key={g.key}>
                    {boxView === "compact" ? (
                      // Header vị trí GỌN: thanh nền tint, tách bạch rõ với header mã SP bên dưới
                      g.href ? (
                        <a class="kho-cmp-loc" href={g.href}>
                          <span class="kho-cmp-loc-name"><Icon name="tag" size={13} /> {g.name}</span>
                          <span class="kho-cmp-loc-meta">{meta} <Icon name="chevronRight" size={13} /></span>
                        </a>
                      ) : (
                        <div class="kho-cmp-loc">
                          <span class="kho-cmp-loc-name">{g.name}</span>
                          <span class="kho-cmp-loc-meta">{meta}</span>
                        </div>
                      )
                    ) : g.href ? (
                      <a class="kho-group-h" href={g.href}>
                        <b><Icon name="box" size={15} /> {g.name}</b>
                        <span class="muted small">{soVN(tot)} tồn · {g.list.length} thùng →</span>
                      </a>
                    ) : (
                      <div class="kho-group-h">
                        <b>{g.name}</b>
                        <span class="muted small">{soVN(tot)} tồn · {g.list.length} thùng</span>
                      </div>
                    )}
                    {boxView === "compact" ? <CompactBoxList boxes={g.list} /> : <BoxLabelGrid boxes={g.list} />}
                  </section>
                );
              })}
            </div>
          </>
        ) : null}
      </div>
    );
  }

  // ── MẶC ĐỊNH: card từng vị trí kho ──────────────────────────────────────
  return (
    <div class="inv-dash">
      {header}{search}
      {places.length === 0 && unplaced.length === 0 ? (
        <EmptyState>Chưa có vị trí kho. Tạo ở <a href="#/vi-tri">Vị trí kho</a>.</EmptyState>
      ) : (
        <>
          {/* Thùng CHƯA XẾP kho lên ĐẦU (dạng chip) — nhắc xếp vào vị trí */}
          {(() => {
            const un = unplaced.filter(hasStock);
            if (!un.length) return null;
            return (
              <section class="card kho-unplaced-top">
                <div class="kho-unplaced-lbl"><Icon name="box" size={15} /> Chưa xếp kho
                  <span class="muted small"> · {un.length} thùng · {soVN(un.reduce((s, b) => s + rem(b), 0))} tồn</span>
                </div>
                <CompactBoxList boxes={un} />
              </section>
            );
          })()}
          <div class="kho-loc-list">
            {sortedPlaces.map((p) => (
              <LocCard key={p.id} p={p} bs={byPlace.get(p.id) || []} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
