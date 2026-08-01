// Dashboard CHẤT LƯỢNG MÂM KẸO (#/chat-luong) — mỗi THỢ 1 card: ảnh mâm gần nhất +
// trạng thái HÔM NAY (✓ đã chụp mâm / chưa chụp) + dải 7 ngày. Bấm card → chi tiết
// thợ để chụp mâm. Thợ lấy từ danh sách thợ (#/tho) — trang này không tạo thợ.
// Data: listQuality. Realtime quality_changed / workers_changed → tải lại.
// Dùng chung CSS .area-* với trang Vệ sinh khu vực (cùng kiểu bảng báo cáo-ảnh-ngày).
import { useEffect, useRef, useState } from "preact/hooks";
import { listQuality, mediaImageUrl, type QualityRow } from "../api";
import { foldVN } from "../format";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { SearchBar } from "../ui/SearchBar";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { scoreClass } from "../detail/PhotoReportViewer";

let qualityCache: QualityRow[] | null = null;
onRealtime((e) => {
  if (e.type === "quality_changed" || e.type === "workers_changed" || e.type === "resync") qualityCache = null;
});

function dow(ymd: string): string {
  const d = new Date(ymd + "T00:00:00");
  return ["CN", "T2", "T3", "T4", "T5", "T6", "T7"][d.getDay()] || "";
}

export function QualityBoard() {
  const [rows, setRows] = useState<QualityRow[] | null>(qualityCache);
  const [today, setToday] = useState("");
  const [done, setDone] = useState(0);
  const [total, setTotal] = useState(0);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");

  const load = async () => {
    try {
      const b = await listQuality();
      setRows(b.workers); qualityCache = b.workers;
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

  if (err && !rows) return <ErrorState msg={err} onRetry={load} />;
  if (!rows) return <Loading />;

  const nq = foldVN(q.trim());
  const shown = nq ? rows.filter((r) => foldVN(r.name).includes(nq)) : rows;

  return (
    <div class="inv-dash">
      <PageHead title={<span><Icon name="star" size={18} /> Chất lượng mâm kẹo</span>}
        sub="Chụp mâm kẹo thợ làm được mỗi ngày" fallback="#/san_xuat"
        right={<a class="btn small" href="#/tho"><Icon name="users" size={15} /> Danh sách thợ</a>} />

      <div class={"area-summary " + (total > 0 && done >= total ? "all-done" : "")}>
        <Icon name="check" size={16} />
        <span>Hôm nay: <b>{done}/{total}</b> thợ đã chụp mâm</span>
      </div>

      <SearchBar value={q} onInput={setQ} placeholder="Tìm tên thợ…" />

      {rows.length === 0 ? (
        <EmptyState>Chưa có thợ nào. Thêm thợ ở <a href="#/tho">Danh sách thợ</a>.</EmptyState>
      ) : shown.length === 0 ? (
        <EmptyState>Không có thợ khớp "{q.trim()}".</EmptyState>
      ) : (
        <div class="area-grid">
          {shown.map((w) => (
            <a class="area-card" href={`#/chat-luong/${w.id}`} key={w.id}>
              <div class="area-thumb">
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
                    ? `✓ Đã chụp mâm${w.today.photo_count > 1 ? ` · ${w.today.photo_count} ảnh` : ""}`
                    : "Chưa chụp mâm"}
                  {w.today.score_avg != null && (
                    <span class={"area-score " + scoreClass(w.today.score_avg)}>
                      <Icon name="star" size={11} /> {w.today.score_avg}/10
                    </span>
                  )}
                </div>
                {w.last_report && (
                  <div class="muted small">
                    Lần gần nhất: {w.last_report.ymd}{w.last_report.created_by ? ` · ${w.last_report.created_by}` : ""}
                  </div>
                )}
                <div class="area-week">
                  {w.week.map((d) => (
                    <span class={"area-dot " + (d.reported ? "on" : "") + (d.ymd === today ? " today" : "")}
                      key={d.ymd} title={`${dow(d.ymd)} ${d.ymd} — ${d.reported ? "đã chụp mâm" : "chưa"}`} />
                  ))}
                </div>
              </div>
              <Icon name="chevronRight" size={18} class="kg-arrow" />
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
