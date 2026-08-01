// Danh sách BÁO CÁO THEO NGÀY (ảnh + điểm + trao đổi) — DÙNG CHUNG cho vệ sinh khu
// vực (#/khu-vuc/:id) và chất lượng mâm kẹo (#/chat-luong/:id).
// Mỗi ngày 1 thẻ: người chụp/giờ · điểm TB ngày · ảnh (badge điểm + 💬 số bình luận
// của từng ảnh) · nút mở TRAO ĐỔI CỦA CẢ NGÀY · admin xoá báo cáo. Chạm 1 ảnh →
// PhotoReportViewer (phóng to + chấm điểm 0–10 + trao đổi riêng ảnh đó).
import { useState } from "preact/hooks";
import { mediaImageUrl, type DayReport, type PhotoScope } from "../api";
import { dayLabel } from "../format";
import { Icon } from "../ui/Icon";
import { EmptyState } from "../ui/states";
import { Comments } from "./Comments";
import { PhotoReportViewer, scoreClass } from "./PhotoReportViewer";

export function PhotoReportDays({
  scope, reports, isAdmin, busy, onDelete, onChanged, emptyText,
}: {
  scope: PhotoScope;
  reports: DayReport[];
  isAdmin: boolean;
  busy: boolean;
  onDelete: (r: DayReport) => void;
  onChanged: () => void;          // tải lại dữ liệu trang cha (sau khi chấm điểm)
  emptyText: string;
}) {
  const [openChat, setOpenChat] = useState<number | null>(null);   // report id đang mở trao đổi
  const [view, setView] = useState<{ rid: number; idx: number } | null>(null);

  const viewReport = view ? reports.find((r) => r.id === view.rid) : null;

  if (!reports.length) return <EmptyState>{emptyText}</EmptyState>;

  return (
    <>
      {reports.map((r) => (
        <section class="card area-report-card" key={r.id}>
          <div class="row space">
            <b>{dayLabel(r.ymd)}</b>
            <span class="muted small">
              {r.created_by ? `${r.created_by}` : ""}{r.created_at ? ` · ${String(r.created_at).slice(11, 16)}` : ""}
              {isAdmin && (
                <button class="area-del-rep" disabled={busy}
                  title="Xoá báo cáo" onClick={() => onDelete(r)}>
                  <Icon name="trash" size={13} />
                </button>
              )}
            </span>
          </div>

          <div class="prd-badges">
            {r.score_avg != null && (
              <span class={"prd-badge " + scoreClass(r.score_avg)}>
                <Icon name="star" size={12} /> {r.score_avg}/10
                <span class="muted"> ({r.score_count}/{r.images.length} ảnh)</span>
              </span>
            )}
            <button class={"prd-badge as-btn" + (openChat === r.id ? " on" : "")}
              onClick={() => setOpenChat(openChat === r.id ? null : r.id)}>
              <Icon name="chat" size={12} /> Trao đổi {r.comment_count ? `(${r.comment_count})` : ""}
            </button>
          </div>

          {r.note ? <p class="muted small" style={{ margin: "2px 0 6px" }}>{r.note}</p> : null}

          {r.images.length > 0 ? (
            <div class="area-thumbs">
              {r.images.map((im, i) => (
                <button class="prd-thumb" key={im.id} onClick={() => setView({ rid: r.id, idx: i })}
                  title={im.score == null ? "Chạm để chấm điểm / trao đổi" : `Điểm ${im.score}/10`}>
                  <img class="area-thumb-sm" loading="lazy" alt=""
                    src={mediaImageUrl(`/api/media/${scope.report}/${r.id}`, im.id, "thumb")} />
                  {im.score != null && (
                    <span class={"prd-score-tag " + scoreClass(im.score)}>{im.score}</span>
                  )}
                  {im.comment_count > 0 && (
                    <span class="prd-cmt-tag"><Icon name="chat" size={10} /> {im.comment_count}</span>
                  )}
                </button>
              ))}
            </div>
          ) : (
            <p class="muted small t-warn" style={{ margin: 0 }}>⚠ Chưa có ảnh — báo cáo chưa hoàn tất.</p>
          )}

          {openChat === r.id && (
            <div class="prd-chat">
              {/* Trao đổi của CẢ NGÀY (scope báo cáo) — khác trao đổi từng ảnh */}
              <Comments base={`/api/media/${scope.report}/${r.id}`} allowPin={false} />
            </div>
          )}
        </section>
      ))}

      {view && viewReport && (
        <PhotoReportViewer
          scope={scope} entityId={viewReport.id} ymd={viewReport.ymd}
          images={viewReport.images} index={Math.min(view.idx, viewReport.images.length - 1)}
          onIndex={(i) => setView({ rid: viewReport.id, idx: i })}
          onClose={() => setView(null)}
          onChanged={onChanged} />
      )}
    </>
  );
}
