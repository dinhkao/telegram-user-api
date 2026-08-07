// Chi tiết CHẤT LƯỢNG MÂM KẸO của 1 THỢ (#/chat-luong/:worker_id) — chụp mâm kẹo
// HÔM NAY (photo-first qua CameraBox: chụp ≥1 ảnh → tạo báo cáo → upload ảnh), lịch
// sử theo ngày (ảnh thumbnail, admin xoá). Hồ sơ/lương thợ ở #/sx-tho/:name.
// Data: getQualityWorker. Realtime quality_changed → tải lại.
// Dùng chung CSS .area-* với trang Vệ sinh khu vực (cùng kiểu báo cáo-ảnh-ngày).
import { useEffect, useRef, useState } from "preact/hooks";
import {
  getQualityWorker, createQualityReport, deleteQualityReport,
  currentUser, isQualityOnly, QUALITY_SCOPE, type DayReport, type QualityReport,
} from "../api";
import { fmtHourVN } from "../format";
import { onRealtime } from "../realtime";
import { PageHead } from "../ui/PageHead";
import { Icon } from "../ui/Icon";
import { toast, confirmDialog } from "../ui/feedback";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { CameraBox, cameraSupported, uploadProcessed, type Processed } from "../detail/CameraBox";
import { ProductPick, readProduct, saveProduct } from "../detail/ProductPick";
import { PhotoReportDays } from "../detail/PhotoReportDays";

export function QualityDetail({ id }: { id: string }) {
  const wid = Number(id);
  const [data, setData] = useState<Awaited<ReturnType<typeof getQualityWorker>> | null | undefined>(undefined);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [camOpen, setCamOpen] = useState(false);
  const capsRef = useRef<Processed[]>([]);
  const isAdmin = currentUser()?.role === "admin";
  const [product, setProduct] = useState(readProduct);   // dùng chung lựa chọn với bảng

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
        try { await uploadProcessed(`/api/media/quality_report/${report_id}`, p, undefined, product); okCount++; }
        catch { /* đếm ảnh lỗi, báo bên dưới */ }
      }
      if (caps.length && okCount === 0)
        toast("⚠ Tạo báo cáo nhưng upload ảnh LỖI — chưa tính là đã chụp mâm. Bấm lại để chụp/tải lại ảnh.", "err");
      else if (okCount < caps.length)
        toast(`⚠ Đã lưu ${okCount} ảnh, ${caps.length - okCount} ảnh upload lỗi.`, "err");
      else
        toast(`✅ Đã chụp mâm kẹo${caps.length ? ` · ${caps.length} ảnh` : ""}${product ? ` · ${product}` : ""}`, "ok");
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
        right={isQualityOnly() ? undefined :   /* vai trò chat_luong không vào được trang SX */
          <a class="btn small" href={`#/sx-tho/${encodeURIComponent(data.worker.name)}`}>
            <Icon name="factory" size={15} /> Sản xuất của thợ
          </a>} />

      {todayDone ? (
        <div class="area-today-ok">
          <Icon name="check" size={18} />
          <span>Hôm nay đã chụp {todayReport?.photo_count || todayReport?.images.length} mâm
            {todayReport?.created_at ? ` (lúc ${fmtHourVN(todayReport.created_at)})` : ""}.</span>
        </div>
      ) : null}

      <div class="qp-bar">
        <ProductPick value={product} onChange={(c) => { setProduct(c); saveProduct(c); }} />
        {!product && <span class="muted small">Chưa chọn — ảnh sẽ không có sản phẩm</span>}
      </div>

      <button class="btn primary block area-report-btn" disabled={busy} onClick={startReport}>
        <Icon name="camera" size={18} /> {todayDone ? "Chụp thêm mâm" : "Chụp mâm kẹo hôm nay"}
      </button>

      {/* Lịch sử báo cáo theo ngày — ảnh + chấm điểm + trao đổi (dùng chung với vệ sinh) */}
      <h3 class="area-hist-h"><Icon name="history" size={16} /> Lịch sử chụp mâm</h3>
      <PhotoReportDays
        scope={QUALITY_SCOPE} reports={data.reports as DayReport[]}
        isAdmin={isAdmin} busy={busy}
        onDelete={(r) => doDeleteReport(r as QualityReport)}
        onChanged={load}
        subject={data.worker.name} subjectLabel="Thợ"
        emptyText="Chưa có ảnh mâm kẹo nào của thợ này. Bấm nút trên để chụp lần đầu." />

      {camOpen && (
        <CameraBox base={`/api/media/quality_report/0`}
          captureOnly
          onCapture={(p) => capsRef.current.push(p)}
          onUploaded={() => { /* collect mode — không upload ngay */ }}
          onClose={() => { setCamOpen(false); finalizeReport(capsRef.current, true); }} />
      )}
    </div>
  );
}
