// Dashboard CHẤT LƯỢNG MÂM KẸO (#/chat-luong) — LƯỚI 2 CỘT, mỗi THỢ 1 card: ảnh mâm
// gần nhất + trạng thái HÔM NAY (✓ đã chụp mâm / chưa chụp) + dải 7 ngày + nút CHỤP
// NHANH (chụp ngay tại bảng, khỏi vào trang chi tiết). Bấm card → chi tiết thợ.
// ⚙ Cài đặt (văn phòng): chọn THỢ NÀO hiện + KÉO sắp THỨ TỰ ô — vì chỉ vài thợ sửa
// kẹo. Cấu hình lưu SERVER (settings_store['quality_board_workers']) nên mọi máy
// giống nhau; chưa cấu hình = hiện tất cả thợ.
// Data: listQuality / setQualityBoardWorkers. Realtime quality_changed / workers_changed.
// Dùng chung CSS .area-* với trang Vệ sinh khu vực; riêng lưới 2 cột là .qb-*.
import { useEffect, useRef, useState } from "preact/hooks";
import { createPortal } from "preact/compat";
import {
  listQuality, setQualityBoardWorkers, createQualityReport, mediaImageUrl,
  isOffice, type QualityRow,
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
import { scoreClass } from "../detail/PhotoReportViewer";

let qualityCache: QualityRow[] | null = null;
onRealtime((e) => {
  if (e.type === "quality_changed" || e.type === "workers_changed" || e.type === "resync") qualityCache = null;
});

function dow(ymd: string): string {
  const d = new Date(ymd + "T00:00:00");
  return ["CN", "T2", "T3", "T4", "T5", "T6", "T7"][d.getDay()] || "";
}

/** Lọc + sắp thợ theo cấu hình bảng; chưa cấu hình ([]) = giữ nguyên tất cả. */
function applyBoard(rows: QualityRow[], ids: number[]): QualityRow[] {
  if (!ids.length) return rows;
  const by = new Map(rows.map((r) => [r.id, r]));
  return ids.map((id) => by.get(id)).filter(Boolean) as QualityRow[];
}

export function QualityBoard() {
  const [rows, setRows] = useState<QualityRow[] | null>(qualityCache);
  const [board, setBoard] = useState<number[]>([]);
  const [today, setToday] = useState("");
  const [done, setDone] = useState(0);
  const [total, setTotal] = useState(0);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [setOpen, setSetOpen] = useState(false);
  const [shootFor, setShootFor] = useState<QualityRow | null>(null);
  const [busy, setBusy] = useState(false);
  const capsRef = useRef<Processed[]>([]);
  const office = isOffice();

  const load = async () => {
    try {
      const b = await listQuality();
      setRows(b.workers); qualityCache = b.workers;
      setBoard(b.board_worker_ids);
      setToday(b.today_ymd); setDone(b.done_count); setTotal(b.total); setErr("");
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
        try { await uploadProcessed(`/api/media/quality_report/${report_id}`, p); ok++; }
        catch { /* đếm ảnh lỗi, báo bên dưới */ }
      }
      if (ok === 0) toast("⚠ Tạo báo cáo nhưng upload ảnh LỖI — chưa tính là đã chụp mâm.", "err");
      else if (ok < caps.length) toast(`⚠ Đã lưu ${ok} ảnh, ${caps.length - ok} ảnh lỗi.`, "err");
      else toast(`✅ ${w.name}: đã chụp ${ok} mâm`, "ok");
      await load();
    } catch (e: any) { toast(e?.message || "Lỗi chụp mâm", "err"); }
    finally { setBusy(false); }
  };

  if (err && !rows) return <ErrorState msg={err} onRetry={load} />;
  if (!rows) return <Loading />;

  const nq = foldVN(q.trim());
  const onBoard = applyBoard(rows, board);
  const shown = nq ? onBoard.filter((r) => foldVN(r.name).includes(nq)) : onBoard;

  return (
    <div class="inv-dash">
      <PageHead title={<span><Icon name="star" size={18} /> Chất lượng mâm kẹo</span>}
        sub="Chụp mâm kẹo thợ làm được mỗi ngày" fallback="#/san_xuat"
        right={
          <span class="row" style={{ gap: "6px" }}>
            {office && (
              <button class="btn small" onClick={() => setSetOpen(true)} title="Chọn thợ hiện trên bảng">
                <Icon name="settings" size={15} /> Cài đặt
              </button>
            )}
            <a class="btn small" href="#/tho"><Icon name="users" size={15} /> Thợ</a>
          </span>
        } />

      <div class={"area-summary " + (total > 0 && done >= total ? "all-done" : "")}>
        <Icon name="check" size={16} />
        <span>Hôm nay: <b>{done}/{total}</b> thợ đã chụp mâm</span>
      </div>

      <SearchBar value={q} onInput={setQ} placeholder="Tìm tên thợ…" />

      {rows.length === 0 ? (
        <EmptyState>Chưa có thợ nào. Thêm thợ ở <a href="#/tho">Danh sách thợ</a>.</EmptyState>
      ) : onBoard.length === 0 ? (
        <EmptyState>
          Cài đặt đang không chọn thợ nào.{" "}
          {office ? <a href="#" onClick={(e: any) => { e.preventDefault(); setSetOpen(true); }}>Mở cài đặt</a>
            : "Nhờ văn phòng mở cài đặt để chọn thợ."}
        </EmptyState>
      ) : shown.length === 0 ? (
        <EmptyState>Không có thợ khớp "{q.trim()}".</EmptyState>
      ) : (
        <div class="area-grid qb-2col">
          {shown.map((w) => (
            <div class="qb-cell" key={w.id}>
              <a class="area-card qb-card" href={`#/chat-luong/${w.id}`}>
                <div class="area-thumb qb-thumb">
                  {w.thumb_image_id != null && w.thumb_report_id != null ? (
                    <img loading="lazy" alt=""
                      src={mediaImageUrl(`/api/media/quality_report/${w.thumb_report_id}`, w.thumb_image_id, "thumb")} />
                  ) : (
                    <span class="area-thumb-ph"><Icon name="camera" size={22} /></span>
                  )}
                </div>
                <div class="area-card-body">
                  <div class="area-card-name">{w.name}</div>
                  <div class={"area-badge " + (w.today.reported ? "t-ok" : "t-danger")}>
                    {w.today.reported
                      ? `✓ Đã chụp${w.today.photo_count > 1 ? ` · ${w.today.photo_count}` : ""}`
                      : "Chưa chụp mâm"}
                    {w.today.score_avg != null && (
                      <span class={"area-score " + scoreClass(w.today.score_avg)}>
                        <Icon name="star" size={11} /> {w.today.score_avg}/10
                      </span>
                    )}
                  </div>
                  <div class="area-week">
                    {w.week.map((d) => (
                      <span class={"area-dot " + (d.reported ? "on" : "") + (d.ymd === today ? " today" : "")}
                        key={d.ymd} title={`${dow(d.ymd)} ${d.ymd} — ${d.reported ? "đã chụp mâm" : "chưa"}`} />
                    ))}
                  </div>
                </div>
              </a>
              {/* NGOÀI thẻ <a> (không lồng button trong link) — bấm là mở camera ngay */}
              <button class="qb-shot" disabled={busy} title={`Chụp mâm cho ${w.name}`}
                onClick={() => startShoot(w)}>
                <Icon name="camera" size={18} />
              </button>
            </div>
          ))}
        </div>
      )}

      {setOpen && (
        <BoardSettings rows={rows} board={board}
          onClose={() => setSetOpen(false)}
          onSaved={(ids) => { setBoard(ids); setSetOpen(false); load(); }} />
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

// ── Popup CÀI ĐẶT: tick thợ hiện trên bảng + kéo sắp thứ tự ô ─────────────────
function BoardSettings({
  rows, board, onClose, onSaved,
}: {
  rows: QualityRow[];
  board: number[];
  onClose: () => void;
  onSaved: (ids: number[]) => void;
}) {
  // Thứ tự ban đầu: thợ ĐANG hiện (đúng thứ tự đã sắp) trước, thợ còn lại sau.
  const initial = (): RItem[] => {
    const by = new Map(rows.map((r) => [r.id, r]));
    const picked = board.map((id) => by.get(id)).filter(Boolean) as QualityRow[];
    const rest = rows.filter((r) => !board.includes(r.id));
    const on = board.length > 0;
    return [...picked.map((r) => ({ id: r.id, name: r.name, on: true })),
            ...rest.map((r) => ({ id: r.id, name: r.name, on: !on }))];
  };
  const [draft, setDraft] = useState<RItem[]>(initial);
  const [busy, setBusy] = useState(false);
  useScrollLock(true);
  usePopupBack(true, onClose);

  const picked = draft.filter((d) => d.on);

  const save = async () => {
    setBusy(true);
    try {
      const ids = await setQualityBoardWorkers(picked.map((d) => Number(d.id)));
      toast(ids.length ? `✅ Bảng hiện ${ids.length} thợ` : "✅ Bảng hiện lại TẤT CẢ thợ", "ok");
      onSaved(ids);
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
          Tick thợ có sửa kẹo · kéo ≡ để đổi vị trí ô (xếp trái→phải, trên→dưới, 2 cột).
          Bỏ tick hết = hiện lại tất cả thợ.
        </p>

        <div class="qb-set-list">
          <ReorderList items={draft} seedSig={rows.length}
            onReorder={(ids) => setDraft((l) => ids.map((i) => l.find((x) => x.id === i)!).filter(Boolean))}
            onToggle={(id, next) => setDraft((l) => l.map((x) => (x.id === id ? { ...x, on: next } : x)))} />
        </div>

        <div class="qb-set-bar">
          <span class="muted small">{picked.length ? `${picked.length} thợ được chọn` : "Chưa chọn ai → hiện tất cả"}</span>
          <button class="btn primary" disabled={busy} onClick={save}>Lưu</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
