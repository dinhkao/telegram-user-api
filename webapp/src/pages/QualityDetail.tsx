// Chi tiết CHẤT LƯỢNG MÂM KẸO của 1 THỢ (#/chat-luong/:worker_id) — chụp mâm kẹo
// HÔM NAY (photo-first qua CameraBox: chụp ≥1 ảnh → tạo báo cáo → upload ảnh), lịch
// sử theo ngày (ảnh thumbnail, admin xoá). Hồ sơ/lương thợ ở #/sx-tho/:name.
// Data: getQualityWorker. Realtime quality_changed → tải lại.
// Dùng chung CSS .area-* với trang Vệ sinh khu vực (cùng kiểu báo cáo-ảnh-ngày).
import { useEffect, useRef, useState } from "preact/hooks";
import {
  getQualityWorker, createQualityReport, deleteQualityReport,
  mediaImageUrl, currentUser, type QualityReport,
} from "../api";
import { dayLabel } from "../format";
import { onRealtime } from "../realtime";
import { PageHead } from "../ui/PageHead";
import { Icon } from "../ui/Icon";
import { toast, confirmDialog } from "../ui/feedback";
import { useScrollLock } from "../useScrollLock";
import { usePopupBack } from "../ui/usePopupBack";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { CameraBox, cameraSupported, uploadProcessed, type Processed } from "../detail/CameraBox";

export function QualityDetail({ id }: { id: string }) {
  const wid = Number(id);
  const [data, setData] = useState<Awaited<ReturnType<typeof getQualityWorker>> | null | undefined>(undefined);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [camOpen, setCamOpen] = useState(false);
  const capsRef = useRef<Processed[]>([]);
  const [lightbox, setLightbox] = useState<{ base: string; imgId: number } | null>(null);
  useScrollLock(!!lightbox);                          // ảnh phóng to phủ màn → khoá cuộn nền
  usePopupBack(!!lightbox, () => setLightbox(null));  // BACK đóng ảnh trước
  const isAdmin = currentUser()?.role === "admin";

  const load = async () => {
    try { setData(await getQualityWorker(wid)); setErr(""); }
    catch (e: any) { setErr(e?.message || "Lỗi tải thợ"); setData(null); }
  };
  useEffect(() => { load(); }, [wid]);
  useEffect(() => onRealtime((e) => {
    if (e.type === "quality_changed" || e.type === "resync") load();
  }), [wid]);

  const todayReport: QualityReport | undefined =
    data?.reports.find((r) => r.ymd === data.today_ymd);
  const todayDone = !!todayReport && (todayReport.photo_count > 0 || todayReport.images.length > 0);

  // Photo-first: chụp vào buffer, đóng camera → tạo/lấy báo cáo hôm nay → upload ảnh.
  const startReport = () => {
    if (!cameraSupported()) {
      // HTTP dev (không camera): tạo báo cáo không ảnh để không kẹt luồng thử.
      finalizeReport([], false);
      return;
    }
    capsRef.current = [];
    setCamOpen(true);
  };

  const finalizeReport = async (caps: Processed[], requirePhoto: boolean) => {
    if (requirePhoto && caps.length === 0) {
      toast("⚠ Chưa chụp ảnh — CHƯA báo cáo. Bấm lại để chụp mâm.", "err");
      return;
    }
    setBusy(true);
    try {
      const { report_id } = await createQualityReport(wid);
      let okCount = 0;
      for (const p of caps) {
        try { await uploadProcessed(`/api/media/quality_report/${report_id}`, p); okCount++; }
        catch { /* đếm ảnh lỗi, báo bên dưới */ }
      }
      if (caps.length && okCount === 0)
        toast("⚠ Tạo báo cáo nhưng upload ảnh LỖI — chưa tính là đã chụp mâm. Bấm lại để chụp/tải lại ảnh.", "err");
      else if (okCount < caps.length)
        toast(`⚠ Đã lưu ${okCount} ảnh, ${caps.length - okCount} ảnh upload lỗi.`, "err");
      else
        toast(`✅ Đã chụp mâm kẹo${caps.length ? ` · ${caps.length} ảnh` : ""}`, "ok");
      await load();
    } catch (e: any) {
      toast(e?.message || "Lỗi báo cáo chất lượng mâm", "err");
    } finally {
      setBusy(false);
    }
  };

  const doDeleteReport = async (r: QualityReport) => {
    if (!(await confirmDialog(`Xoá báo cáo chất lượng mâm ngày ${r.ymd}?`,
      { danger: true, okLabel: "Xoá báo cáo" }))) return;
    setBusy(true);
    try { await deleteQualityReport(r.id); toast("Đã xoá báo cáo", "ok"); await load(); }
    catch (e: any) { toast(e?.message || "Lỗi xoá báo cáo", "err"); }
    finally { setBusy(false); }
  };

  if (err && data === null) return <ErrorState msg={err} onRetry={load} />;
  if (data === undefined) return <Loading />;
  if (data === null) return <EmptyState>Không tìm thấy thợ. <a href="#/chat-luong">← Chất lượng mâm kẹo</a></EmptyState>;

  return (
    <div class="inv-dash">
      <PageHead title={<span><Icon name="star" size={18} /> {data.worker.name}</span>}
        sub="Chất lượng mâm kẹo" fallback="#/chat-luong"
        right={<a class="btn small" href={`#/sx-tho/${encodeURIComponent(data.worker.name)}`}>
          <Icon name="factory" size={15} /> Sản xuất của thợ
        </a>} />

      {todayDone ? (
        <div class="area-today-ok">
          <Icon name="check" size={18} />
          <span>Hôm nay đã chụp {todayReport?.photo_count || todayReport?.images.length} mâm
            {todayReport?.created_at ? ` (lúc ${String(todayReport.created_at).slice(11, 16)})` : ""}.</span>
        </div>
      ) : null}

      <button class="btn primary block area-report-btn" disabled={busy} onClick={startReport}>
        <Icon name="camera" size={18} /> {todayDone ? "Chụp thêm mâm" : "Chụp mâm kẹo hôm nay"}
      </button>

      {/* Lịch sử báo cáo theo ngày */}
      <h3 class="area-hist-h"><Icon name="history" size={16} /> Lịch sử chụp mâm</h3>
      {data.reports.length === 0 ? (
        <EmptyState>Chưa có ảnh mâm kẹo nào của thợ này. Bấm nút trên để chụp lần đầu.</EmptyState>
      ) : (
        data.reports.map((r) => {
          const base = `/api/media/quality_report/${r.id}`;
          return (
            <section class="card area-report-card" key={r.id}>
              <div class="row space">
                <b>{dayLabel(r.ymd)}</b>
                <span class="muted small">
                  {r.created_by ? `${r.created_by}` : ""}{r.created_at ? ` · ${String(r.created_at).slice(11, 16)}` : ""}
                  {isAdmin && (
                    <button class="area-del-rep" disabled={busy}
                      title="Xoá báo cáo" onClick={() => doDeleteReport(r)}>
                      <Icon name="trash" size={13} />
                    </button>
                  )}
                </span>
              </div>
              {r.note ? <p class="muted small" style={{ margin: "2px 0 6px" }}>{r.note}</p> : null}
              {r.images.length > 0 ? (
                <div class="area-thumbs">
                  {r.images.map((imgId) => (
                    <img class="area-thumb-sm" loading="lazy" alt="" key={imgId}
                      src={mediaImageUrl(base, imgId, "thumb")}
                      onClick={() => setLightbox({ base, imgId })} />
                  ))}
                </div>
              ) : (
                <p class="muted small t-warn" style={{ margin: 0 }}>⚠ Chưa có ảnh — báo cáo chưa hoàn tất.</p>
              )}
            </section>
          );
        })
      )}

      {camOpen && (
        <CameraBox base={`/api/media/quality_report/0`}
          onCapture={(p) => capsRef.current.push(p)}
          onUploaded={() => { /* collect mode — không upload ngay */ }}
          onClose={() => { setCamOpen(false); finalizeReport(capsRef.current, true); }} />
      )}

      {lightbox && (
        <div class="cam-overlay" onClick={() => setLightbox(null)}>
          <img class="area-lightbox-img" alt=""
            src={mediaImageUrl(lightbox.base, lightbox.imgId, "full")} />
        </div>
      )}
    </div>
  );
}
