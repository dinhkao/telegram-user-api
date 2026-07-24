// Chi tiết 1 KHU VỰC XƯỞNG (#/khu-vuc/:id) — báo cáo vệ sinh HÔM NAY (photo-first
// qua CameraBox: chụp ≥1 ảnh → tạo báo cáo → upload ảnh), lịch sử báo cáo theo ngày
// (ảnh thumbnail, xoá admin). Sửa tên/ghi chú (văn phòng), xoá khu vực (admin).
// Data: getArea. Realtime area_changed → tải lại.
import { useEffect, useRef, useState } from "preact/hooks";
import {
  getArea, createAreaReport, updateArea, deleteArea, deleteAreaReport,
  mediaImageUrl, currentUser, isOffice, type AreaReport,
} from "../api";
import { dayLabel } from "../format";
import { onRealtime } from "../realtime";
import { PageHead } from "../ui/PageHead";
import { Icon } from "../ui/Icon";
import { toast, confirmDialog, promptDialog } from "../ui/feedback";
import { Loading, EmptyState, ErrorState } from "../ui/states";
import { CameraBox, cameraSupported, uploadProcessed, type Processed } from "../detail/CameraBox";

export function AreaDetail({ id }: { id: string }) {
  const aid = Number(id);
  const [data, setData] = useState<Awaited<ReturnType<typeof getArea>> | null | undefined>(undefined);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [camOpen, setCamOpen] = useState(false);
  const capsRef = useRef<Processed[]>([]);
  const [lightbox, setLightbox] = useState<{ base: string; imgId: number } | null>(null);
  const isAdmin = currentUser()?.role === "admin";
  const office = isOffice();

  const load = async () => {
    try { setData(await getArea(aid)); setErr(""); }
    catch (e: any) { setErr(e?.message || "Lỗi tải khu vực"); setData(null); }
  };
  useEffect(() => { load(); }, [aid]);
  useEffect(() => onRealtime((e) => {
    if (e.type === "area_changed" || e.type === "resync") load();
  }), [aid]);

  const todayReport: AreaReport | undefined =
    data?.reports.find((r) => r.ymd === data.today_ymd);
  const todayDone = !!todayReport && (todayReport.photo_count > 0 || todayReport.images.length > 0);

  // Photo-first: chụp vào buffer, đóng camera → tạo/lấy báo cáo hôm nay → upload ảnh.
  const startReport = () => {
    const camOk = cameraSupported();
    if (!camOk) {
      // HTTP dev (không camera): tạo báo cáo không ảnh để không kẹt luồng thử.
      finalizeReport([], false);
      return;
    }
    capsRef.current = [];
    setCamOpen(true);
  };

  const finalizeReport = async (caps: Processed[], requirePhoto: boolean) => {
    if (requirePhoto && caps.length === 0) {
      toast("⚠ Chưa chụp ảnh — CHƯA báo cáo. Bấm lại để làm.", "err");
      return;
    }
    setBusy(true);
    try {
      const { report_id } = await createAreaReport(aid);
      let okCount = 0;
      for (const p of caps) {
        try { await uploadProcessed(`/api/media/area_report/${report_id}`, p); okCount++; }
        catch { /* đếm ảnh lỗi, báo bên dưới */ }
      }
      if (caps.length && okCount === 0)
        toast("⚠ Tạo báo cáo nhưng upload ảnh LỖI — chưa tính là đã vệ sinh. Bấm lại để chụp/tải lại ảnh.", "err");
      else if (okCount < caps.length)
        toast(`⚠ Đã lưu ${okCount} ảnh, ${caps.length - okCount} ảnh upload lỗi.`, "err");
      else
        toast(`✅ Đã báo cáo vệ sinh${caps.length ? ` · ${caps.length} ảnh` : ""}`, "ok");
      await load();
    } catch (e: any) {
      toast(e?.message || "Lỗi báo cáo vệ sinh", "err");
    } finally {
      setBusy(false);
    }
  };

  const editArea = async () => {
    if (!data) return;
    const name = (await promptDialog("Đổi tên khu vực", { initial: data.area.name, okLabel: "Lưu" }))?.trim();
    if (name == null || name === "" || name === data.area.name) return;
    setBusy(true);
    try { await updateArea(aid, { name }); toast("✅ Đã đổi tên", "ok"); await load(); }
    catch (e: any) { toast(e?.message || "Lỗi đổi tên", "err"); }
    finally { setBusy(false); }
  };

  const editNote = async () => {
    if (!data) return;
    const note = await promptDialog("Ghi chú khu vực", { initial: data.area.note || "", okLabel: "Lưu" });
    if (note == null) return;
    setBusy(true);
    try { await updateArea(aid, { note }); toast("✅ Đã lưu ghi chú", "ok"); await load(); }
    catch (e: any) { toast(e?.message || "Lỗi lưu ghi chú", "err"); }
    finally { setBusy(false); }
  };

  const doDelete = async () => {
    if (!data) return;
    if (!(await confirmDialog(`Xoá khu vực "${data.area.name}"? Báo cáo cũ vẫn giữ nhưng khu vực sẽ ẩn khỏi bảng.`,
      { danger: true, okLabel: "Xoá" }))) return;
    setBusy(true);
    try { await deleteArea(aid); window.location.hash = "#/khu-vuc"; }
    catch (e: any) { toast(e?.message || "Lỗi xoá", "err"); setBusy(false); }
  };

  const doDeleteReport = async (r: AreaReport) => {
    if (!(await confirmDialog(`Xoá báo cáo vệ sinh ngày ${r.ymd}?`, { danger: true, okLabel: "Xoá" }))) return;
    setBusy(true);
    try { await deleteAreaReport(r.id); toast("Đã xoá báo cáo", "ok"); await load(); }
    catch (e: any) { toast(e?.message || "Lỗi xoá báo cáo", "err"); }
    finally { setBusy(false); }
  };

  if (err && data === null) return <ErrorState msg={err} onRetry={load} />;
  if (data === undefined) return <Loading />;
  if (data === null) return <EmptyState>Không tìm thấy khu vực. <a href="#/khu-vuc">← Khu vực xưởng</a></EmptyState>;

  return (
    <div class="inv-dash">
      <PageHead title={<span onClick={office ? editArea : undefined} style={office ? { cursor: "pointer" } : undefined}>
        <Icon name="leaf" size={18} /> {data.area.name}{office ? <Icon name="edit" size={14} class="kg-arrow" /> : null}
      </span>} sub="Vệ sinh khu vực" fallback="#/khu-vuc" />

      <section class="card">
        <label class="card-label" onClick={office ? editNote : undefined} style={office ? { cursor: "pointer" } : undefined}>
          <Icon name="edit" size={15} /> Ghi chú {office ? <Icon name="edit" size={12} class="kg-arrow" /> : null}
        </label>
        {data.area.note
          ? <p style={{ whiteSpace: "pre-wrap", margin: "4px 0" }}>{data.area.note}</p>
          : <p class="muted small" style={{ margin: "4px 0" }}>{office ? "Chưa có ghi chú — bấm để thêm." : "Chưa có ghi chú."}</p>}
      </section>

      {todayDone ? (
        <div class="area-today-ok">
          <Icon name="check" size={18} />
          <span>Hôm nay đã báo cáo{todayReport?.created_at ? ` lúc ${String(todayReport.created_at).slice(11, 16)}` : ""}.</span>
        </div>
      ) : null}

      <button class="btn primary block area-report-btn" disabled={busy} onClick={startReport}>
        <Icon name="camera" size={18} /> {todayDone ? "Chụp thêm ảnh" : "Báo cáo vệ sinh hôm nay"}
      </button>

      {/* Lịch sử báo cáo theo ngày */}
      <h3 class="area-hist-h"><Icon name="history" size={16} /> Lịch sử báo cáo</h3>
      {data.reports.length === 0 ? (
        <EmptyState>Chưa có báo cáo vệ sinh nào. Bấm nút trên để báo cáo lần đầu.</EmptyState>
      ) : (
        data.reports.map((r) => {
          const base = `/api/media/area_report/${r.id}`;
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

      {isAdmin && (
        <section class="card" style={{ marginTop: "14px" }}>
          <button class="btn danger block" disabled={busy} onClick={doDelete}>
            <Icon name="trash" size={16} /> Xoá khu vực (admin)
          </button>
        </section>
      )}

      {camOpen && (
        <CameraBox base={`/api/media/area_report/0`}
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
