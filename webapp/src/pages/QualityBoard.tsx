// Dashboard CHẤT LƯỢNG MÂM KẸO (#/chat-luong) — lưới 2 CỘT, mỗi THỢ 1 card + nút
// CHỤP NHANH (chụp ngay tại bảng, khỏi vào trang chi tiết). Bấm card → chi tiết thợ.
// Hai kiểu hiện: ĐẦY ĐỦ (có ảnh mâm gần nhất + dải 7 ngày) và GỌN (chỉ tên + nút
// chụp) — chọn kiểu nào lưu ở MÁY (localStorage), vì đây là sở thích nhìn của từng
// người, khác với cấu hình bảng (lưu server, chung cả tiệm).
// ⚙ Cài đặt (văn phòng): tick thợ hiện + kéo thứ tự + chọn thợ nằm ở CỘT 1 hay CỘT 2.
// 🖼 Nút "Tất cả ảnh" → #/chat-luong/anh.
// Data: listQuality / setQualityBoardColumns. Realtime quality_changed / workers_changed.
import { useEffect, useRef, useState } from "preact/hooks";
import { createPortal } from "preact/compat";
import {
  listQuality, setQualityBoardColumns, createQualityReport, mediaImageUrl,
  isOffice, isQualityOnly, type QualityRow,
} from "../api";
import { foldVN } from "../format";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { SearchBar } from "../ui/SearchBar";
import { toast } from "../ui/feedback";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { useScrollLock } from "../useScrollLock";
import { usePopupBack } from "../ui/usePopupBack";
import { ReorderList, type RItem } from "../detail/ReorderList";
import { CameraBox, cameraSupported, uploadProcessed, type Processed } from "../detail/CameraBox";
import { ProductPick, readProduct, saveProduct } from "../detail/ProductPick";

let qualityCache: QualityRow[] | null = null;
onRealtime((e) => {
  if (e.type === "quality_changed" || e.type === "workers_changed" || e.type === "resync") qualityCache = null;
});

const COMPACT_KEY = "quality_board_compact";
const readCompact = () => { try { return localStorage.getItem(COMPACT_KEY) === "1"; } catch { return false; } };
const saveCompact = (v: boolean) => { try { localStorage.setItem(COMPACT_KEY, v ? "1" : "0"); } catch { /* riêng tư/đầy */ } };

function dow(ymd: string): string {
  const d = new Date(ymd + "T00:00:00");
  return ["CN", "T2", "T3", "T4", "T5", "T6", "T7"][d.getDay()] || "";
}

/** Dựng 2 cột thợ theo cấu hình. Chưa cấu hình (2 cột rỗng) = rải đều tất cả thợ. */
function buildColumns(rows: QualityRow[], columns: number[][]): QualityRow[][] {
  const by = new Map(rows.map((r) => [r.id, r]));
  const cfg = (columns || []).some((c) => c && c.length);
  if (!cfg) {
    const out: QualityRow[][] = [[], []];
    rows.forEach((r, i) => out[i % 2].push(r));
    return out;
  }
  return [0, 1].map((i) => (columns[i] || []).map((id) => by.get(id)).filter(Boolean) as QualityRow[]);
}

export function QualityBoard() {
  const [rows, setRows] = useState<QualityRow[] | null>(qualityCache);
  const [columns, setColumns] = useState<number[][]>([[], []]);
  const [today, setToday] = useState("");
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [setOpen, setSetOpen] = useState(false);
  const [compact, setCompact] = useState(readCompact);
  const [product, setProduct] = useState(readProduct);   // SP gắn cho ảnh chụp sau đó
  const [shootFor, setShootFor] = useState<QualityRow | null>(null);
  const [busy, setBusy] = useState(false);
  const capsRef = useRef<Processed[]>([]);
  const office = isOffice();

  const load = async () => {
    try {
      const b = await listQuality();
      setRows(b.workers); qualityCache = b.workers;
      setColumns(b.board_columns);
      setToday(b.today_ymd); setErr("");
    } catch (e: any) { setErr(e?.message || "Lỗi tải bảng chất lượng"); }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => onRealtime((e) => {
    if (e.type === "quality_changed" || e.type === "workers_changed" || e.type === "resync") load();
  }), []);
  const rowsRef = useRef<QualityRow[]>([]);
  rowsRef.current = rows || [];
  useEffect(() => () => { if (rowsRef.current.length) qualityCache = rowsRef.current; }, []);

  // ── CHỤP NHANH ngay tại bảng: gom ảnh → tạo báo cáo hôm nay → upload ─────────
  const startShoot = (w: QualityRow) => {
    if (!cameraSupported()) { toast("Máy/trình duyệt này không mở được camera (cần HTTPS).", "err"); return; }
    capsRef.current = [];
    setShootFor(w);
  };
  const finishShoot = async (w: QualityRow, caps: Processed[]) => {
    if (!caps.length) { toast("⚠ Chưa chụp ảnh — CHƯA báo cáo.", "err"); return; }
    setBusy(true);
    try {
      const { report_id } = await createQualityReport(w.id);
      let ok = 0;
      for (const p of caps) {
        try { await uploadProcessed(`/api/media/quality_report/${report_id}`, p, undefined, product); ok++; }
        catch { /* đếm ảnh lỗi, báo bên dưới */ }
      }
      if (ok === 0) toast("⚠ Tạo báo cáo nhưng upload ảnh LỖI — chưa tính là đã chụp mâm.", "err");
      else if (ok < caps.length) toast(`⚠ Đã lưu ${ok} ảnh, ${caps.length - ok} ảnh lỗi.`, "err");
      else toast(`✅ ${w.name}: đã chụp ${ok} mâm${product ? ` · ${product}` : ""}`, "ok");
      await load();
    } catch (e: any) { toast(e?.message || "Lỗi chụp mâm", "err"); }
    finally { setBusy(false); }
  };

  if (err && !rows) return <ErrorState msg={err} onRetry={load} />;
  if (!rows) return <Loading />;

  const nq = foldVN(q.trim());
  const cols = buildColumns(rows, columns).map((c) =>
    nq ? c.filter((r) => foldVN(r.name).includes(nq)) : c);
  const shownCount = cols[0].length + cols[1].length;
  const onBoardCount = buildColumns(rows, columns).reduce((n, c) => n + c.length, 0);

  const card = (w: QualityRow) => (
    <div class="qb-cell" key={w.id}>
      <a class={"area-card qb-card" + (compact ? " qb-card-min" : "")} href={`#/chat-luong/${w.id}`}>
        {!compact && (
          <div class="area-thumb qb-thumb">
            {w.thumb_image_id != null && w.thumb_report_id != null ? (
              <img loading="lazy" alt=""
                src={mediaImageUrl(`/api/media/quality_report/${w.thumb_report_id}`, w.thumb_image_id, "thumb")} />
            ) : (
              <span class="area-thumb-ph"><Icon name="camera" size={22} /></span>
            )}
          </div>
        )}
        <div class="area-card-body">
          <div class="area-card-name">{w.name}</div>
          {/* Không hiện "đã chụp/chưa chụp" và điểm trên card cho gọn — trạng thái
              theo ngày vẫn xem được ở dải 7 chấm bên dưới và trong trang chi tiết. */}
          {!compact && (
            <div class="area-week">
              {w.week.map((d) => (
                <span class={"area-dot " + (d.reported ? "on" : "") + (d.ymd === today ? " today" : "")}
                  key={d.ymd} title={`${dow(d.ymd)} ${d.ymd} — ${d.reported ? "đã chụp mâm" : "chưa"}`} />
              ))}
            </div>
          )}
        </div>
      </a>
      {/* NGOÀI thẻ <a> (không lồng button trong link) — bấm là mở camera ngay */}
      <button class={"qb-shot" + (compact ? " qb-shot-min" : "")} disabled={busy}
        title={`Chụp mâm cho ${w.name}`} onClick={() => startShoot(w)}>
        <Icon name="camera" size={compact ? 16 : 18} />
      </button>
    </div>
  );

  return (
    <div class="inv-dash">
      <PageHead title={<span><Icon name="star" size={18} /> Chất lượng mâm kẹo</span>}
        sub="Chụp mâm kẹo thợ làm được mỗi ngày" fallback="#/san_xuat"
        right={
          <span class="row" style={{ gap: "6px" }}>
            <button class="btn small" title={compact ? "Xem đầy đủ (có ảnh)" : "Xem gọn (chỉ tên + nút chụp)"}
              onClick={() => { const v = !compact; setCompact(v); saveCompact(v); }}>
              <Icon name={compact ? "grid" : "menu"} size={15} /> {compact ? "Đầy đủ" : "Gọn"}
            </button>
            <a class="btn small" href="#/chat-luong/anh" title="Xem tất cả ảnh mâm kẹo">
              <Icon name="image" size={15} /> Ảnh
            </a>
            {office && (
              <button class="btn small" onClick={() => setSetOpen(true)} title="Chọn thợ + cột hiển thị">
                <Icon name="settings" size={15} />
              </button>
            )}
          </span>
        } />

      {/* Sản phẩm sẽ gắn cho MỌI ảnh chụp sau đó (cả nút chụp nhanh lẫn trang thợ) */}
      <div class="qp-bar">
        <ProductPick value={product} onChange={(c) => { setProduct(c); saveProduct(c); }} />
        {!product && <span class="muted small">Chưa chọn — ảnh sẽ không có sản phẩm</span>}
      </div>

      <SearchBar value={q} onInput={setQ} placeholder="Tìm tên thợ…" />

      {rows.length === 0 ? (
        <EmptyState>Chưa có thợ nào.{isQualityOnly()
          ? " Nhờ văn phòng thêm thợ."
          : <> Thêm thợ ở <a href="#/tho">Danh sách thợ</a>.</>}</EmptyState>
      ) : onBoardCount === 0 ? (
        <EmptyState>
          Cài đặt đang không chọn thợ nào.{" "}
          {office ? <a href="#" onClick={(e: any) => { e.preventDefault(); setSetOpen(true); }}>Mở cài đặt</a>
            : "Nhờ văn phòng mở cài đặt để chọn thợ."}
        </EmptyState>
      ) : shownCount === 0 ? (
        <EmptyState>Không có thợ khớp "{q.trim()}".</EmptyState>
      ) : (
        <div class="qb-cols">
          <div class="qb-col">{cols[0].map(card)}</div>
          <div class="qb-col">{cols[1].map(card)}</div>
        </div>
      )}

      {setOpen && (
        <BoardSettings rows={rows} columns={columns}
          onClose={() => setSetOpen(false)}
          onSaved={(c) => { setColumns(c); setSetOpen(false); load(); }} />
      )}

      {shootFor && (
        <CameraBox base={`/api/media/quality_report/0`}
          captureOnly
          onCapture={(p) => capsRef.current.push(p)}
          onUploaded={() => { /* collect mode — upload sau khi có báo cáo */ }}
          onClose={() => { const w = shootFor; setShootFor(null); if (w) finishShoot(w, capsRef.current); }} />
      )}
    </div>
  );
}

// ── Popup CÀI ĐẶT: tick thợ hiện · kéo thứ tự · chọn CỘT 1 / CỘT 2 ───────────
type Draft = RItem & { col: 0 | 1 };

function BoardSettings({
  rows, columns, onClose, onSaved,
}: {
  rows: QualityRow[];
  columns: number[][];
  onClose: () => void;
  onSaved: (columns: number[][]) => void;
}) {
  const initial = (): Draft[] => {
    const by = new Map(rows.map((r) => [r.id, r]));
    const cfg = (columns || []).some((c) => c && c.length);
    const out: Draft[] = [];
    const seen = new Set<number>();
    [0, 1].forEach((ci) => {
      for (const id of (columns[ci] || [])) {
        const r = by.get(id);
        if (r && !seen.has(id)) { seen.add(id); out.push({ id: r.id, name: r.name, on: true, col: ci as 0 | 1 }); }
      }
    });
    rows.forEach((r, i) => {
      if (!seen.has(r.id)) out.push({ id: r.id, name: r.name, on: !cfg, col: (i % 2) as 0 | 1 });
    });
    return out;
  };
  const [draft, setDraft] = useState<Draft[]>(initial);
  const [busy, setBusy] = useState(false);
  useScrollLock(true);
  usePopupBack(true, onClose);

  const picked = draft.filter((d) => d.on);
  const toCols = (): number[][] =>
    [0, 1].map((ci) => picked.filter((d) => d.col === ci).map((d) => Number(d.id)));

  const save = async () => {
    setBusy(true);
    try {
      const c = await setQualityBoardColumns(toCols());
      const n = c.reduce((s, x) => s + x.length, 0);
      toast(n ? `✅ Bảng hiện ${n} thợ (cột 1: ${c[0].length}, cột 2: ${c[1].length})`
              : "✅ Bảng hiện lại TẤT CẢ thợ", "ok");
      onSaved(c);
    } catch (e: any) { toast(e?.message || "Lỗi lưu cài đặt", "err"); }
    finally { setBusy(false); }
  };

  return createPortal(
    <div class="cam-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="qb-set">
        <div class="row space qb-set-head">
          <b><Icon name="settings" size={16} /> Thợ hiện trên bảng</b>
          <button class="prv-x" onClick={onClose} title="Đóng"><Icon name="close" size={20} /></button>
        </div>
        <p class="muted small qb-set-hint">
          Tick thợ có sửa kẹo · kéo ≡ để đổi thứ tự · bấm <b>C1/C2</b> để chọn thợ đó nằm
          cột trái hay cột phải. Bỏ tick hết = hiện lại tất cả thợ.
        </p>

        <div class="qb-set-list">
          <ReorderList items={draft} seedSig={rows.length}
            onReorder={(ids) => setDraft((l) => ids.map((i) => l.find((x) => x.id === i)!).filter(Boolean))}
            onToggle={(id, next) => setDraft((l) => l.map((x) => (x.id === id ? { ...x, on: next } : x)))}
            trailing={(it) => {
              const d = draft.find((x) => x.id === it.id);
              if (!d || !d.on) return null;
              return (
                <button class={"qb-colbtn c" + d.col}
                  title="Đổi cột hiển thị"
                  onClick={(e: any) => {
                    e.preventDefault(); e.stopPropagation();
                    setDraft((l) => l.map((x) => (x.id === it.id ? { ...x, col: (x.col ? 0 : 1) as 0 | 1 } : x)));
                  }}>C{d.col + 1}</button>
              );
            }} />
        </div>

        <div class="qb-set-bar">
          <span class="muted small">
            {picked.length ? `${picked.length} thợ · C1: ${toCols()[0].length} · C2: ${toCols()[1].length}`
                           : "Chưa chọn ai → hiện tất cả"}
          </span>
          <button class="btn primary" disabled={busy} onClick={save}>Lưu</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
