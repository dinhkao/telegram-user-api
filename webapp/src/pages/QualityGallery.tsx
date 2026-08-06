// XEM TẤT CẢ ẢNH MÂM KẸO (#/chat-luong/anh) — mọi ảnh gần đây gom theo NGÀY rồi
// theo THỢ, mới nhất trước. Chạm 1 ảnh → PhotoReportViewer (phóng to + chấm điểm
// + trao đổi), dùng CHUNG component với trang chi tiết thợ nên chấm ở đây cũng được.
// Lọc theo thợ + đổi khoảng ngày (7/14/30/60). Data: getQualityGallery.
// Realtime quality_changed → tải lại.
import { useEffect, useMemo, useState } from "preact/hooks";
import {
  getQualityGallery, mediaImageUrl, QUALITY_SCOPE,
  type QualityGalleryGroup,
} from "../api";
import { dayLabel, fmtHourVN, foldVN } from "../format";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { SearchBar } from "../ui/SearchBar";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { PhotoReportViewer, scoreClass } from "../detail/PhotoReportViewer";

const RANGES = [7, 14, 30, 60];

export function QualityGallery() {
  const [groups, setGroups] = useState<QualityGalleryGroup[] | null>(null);
  const [total, setTotal] = useState(0);
  const [days, setDays] = useState(14);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [todo, setTodo] = useState(false);     // chỉ hiện ảnh TÔI chưa chấm
  // ids = ẢNH ĐANG MỞ chốt lúc bấm vào. Không lấy thẳng danh sách đã lọc, vì khi
  // đang lọc "chưa chấm" mà chấm xong thì ảnh rớt khỏi bộ lọc → viewer nhảy ảnh
  // giữa chừng. Chốt danh sách rồi mới tra điểm mới nhất theo id.
  const [view, setView] = useState<{ rid: number; idx: number; ids: number[] } | null>(null);

  const load = async (d = days) => {
    try {
      const r = await getQualityGallery(d);
      setGroups(r.groups); setTotal(r.total_images); setErr("");
    } catch (e: any) { setErr(e?.message || "Lỗi tải ảnh"); }
  };
  useEffect(() => { load(days); }, [days]);
  useEffect(() => onRealtime((e) => {
    if (e.type === "quality_changed" || e.type === "resync") load();
  }), [days]);

  const nq = foldVN(q.trim());
  // số ảnh CHÍNH TÔI chưa chấm (my_score = null) — hiện lên nút lọc
  const todoCount = useMemo(
    () => (groups || []).reduce((n, g) => n + g.images.filter((im) => im.my_score == null).length, 0),
    [groups]);
  const shown = useMemo(() => {
    let gs = groups || [];
    if (nq) gs = gs.filter((g) => foldVN(g.worker_name).includes(nq));
    if (todo) {
      gs = gs.map((g) => ({ ...g, images: g.images.filter((im) => im.my_score == null) }))
             .filter((g) => g.images.length > 0);
    }
    return gs;
  }, [groups, nq, todo]);

  // gom theo NGÀY để có tiêu đề ngày, trong mỗi ngày là các thợ
  const byDay = useMemo(() => {
    const m = new Map<string, QualityGalleryGroup[]>();
    for (const g of shown) {
      const a = m.get(g.ymd) || [];
      a.push(g); m.set(g.ymd, a);
    }
    return [...m.entries()];
  }, [shown]);

  // Ảnh cho viewer: theo danh sách ĐÃ CHỐT lúc mở, nhưng lấy bản mới nhất (điểm vừa
  // chấm cập nhật ngay) — nên chấm xong ảnh KHÔNG biến mất khỏi viewer.
  const viewGroup = view ? (groups || []).find((g) => g.report_id === view.rid) : null;
  const viewImages = view && viewGroup
    ? view.ids.map((id) => viewGroup.images.find((im) => im.id === id)).filter(Boolean) as typeof viewGroup.images
    : [];

  if (err && !groups) return <ErrorState msg={err} onRetry={() => load()} />;
  if (!groups) return <Loading />;

  return (
    <div class="inv-dash">
      <PageHead title={<span><Icon name="image" size={18} /> Tất cả ảnh mâm kẹo</span>}
        sub={`${total} ảnh trong ${days} ngày gần đây`} fallback="#/chat-luong" />

      <div class="qg-range">
        {RANGES.map((d) => (
          <button key={d} class={"btn small" + (d === days ? " primary" : "")}
            onClick={() => setDays(d)}>{d} ngày</button>
        ))}
        {/* Lọc "tôi chưa chấm" — điểm là riêng từng người nên đây là việc CỦA BẠN */}
        <button class={"btn small qg-todo" + (todo ? " primary" : "")}
          title="Chỉ hiện ảnh bạn chưa chấm điểm"
          onClick={() => setTodo((v) => !v)}>
          <Icon name="star" size={14} /> Chưa chấm{todoCount ? ` (${todoCount})` : ""}
        </button>
      </div>

      <SearchBar value={q} onInput={setQ} placeholder="Lọc theo tên thợ…" />

      {byDay.length === 0 ? (
        <EmptyState>{todo ? "🎉 Bạn đã chấm hết ảnh trong khoảng này."
          : q.trim() ? `Không có ảnh của thợ khớp "${q.trim()}".`
          : "Chưa có ảnh mâm kẹo nào trong khoảng này."}</EmptyState>
      ) : byDay.map(([ymd, gs]) => (
        <section class="card qg-day" key={ymd}>
          <div class="row space">
            <b>{dayLabel(ymd)}</b>
            <span class="muted small">{gs.reduce((n, g) => n + g.images.length, 0)} ảnh</span>
          </div>
          {gs.map((g) => (
            <div class="qg-worker" key={g.report_id}>
              <div class="qg-worker-head">
                <a class="qg-worker-name" href={`#/chat-luong/${g.worker_id}`}>
                  <Icon name="user" size={13} /> {g.worker_name}
                </a>
                {g.score_avg != null && (
                  <span class={"prd-badge " + scoreClass(g.score_avg)}>
                    <Icon name="star" size={11} /> {g.score_avg}/10
                  </span>
                )}
                <span class="muted small">
                  {g.created_by}{g.created_at ? ` · ${fmtHourVN(g.created_at)}` : ""}
                </span>
              </div>
              <div class="area-thumbs">
                {g.images.map((im, i) => (
                  <button class={"prd-thumb" + (im.my_score == null ? " qg-todo-thumb" : "")} key={im.id}
                    onClick={() => setView({ rid: g.report_id, idx: i, ids: g.images.map((x) => x.id) })}
                    title={im.score == null ? "Chạm để chấm điểm / trao đổi" : `TB ${im.score}/10`}>
                    <img class="area-thumb-sm" loading="lazy" alt=""
                      src={mediaImageUrl(`/api/media/quality_report/${g.report_id}`, im.id, "thumb")} />
                    {im.score != null && (
                      <span class={"prd-score-tag " + scoreClass(im.score)}>{im.score}</span>
                    )}
                    {im.comment_count > 0 && (
                      <span class="prd-cmt-tag"><Icon name="chat" size={10} /> {im.comment_count}</span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </section>
      ))}

      {view && viewGroup && viewImages.length > 0 && (
        <PhotoReportViewer
          scope={QUALITY_SCOPE} entityId={viewGroup.report_id} ymd={viewGroup.ymd}
          images={viewImages} index={Math.min(view.idx, viewImages.length - 1)}
          onIndex={(i) => setView({ ...view, idx: i })}
          onClose={() => setView(null)}
          subject={viewGroup.worker_name} subjectLabel="Thợ"
          reportBy={viewGroup.created_by} reportAt={viewGroup.created_at}
          onChanged={() => load()} />
      )}
    </div>
  );
}
