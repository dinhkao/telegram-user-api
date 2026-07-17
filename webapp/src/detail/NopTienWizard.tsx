// Wizard nộp tiền — bê từ bot Telegram (bot_flows/nop_wizard). Chọn loại → có loại
// bắt gửi ảnh (tiền mặt+toa / toa có chữ ký). Ảnh upload vào /api/order/{id}/images
// (tự đồng bộ sang topic). Ghi task nop_tien với note + done như bot.
import { useRef, useState } from "preact/hooks";
import { postJSON, postForm } from "../api";
import { processImage } from "./imageProcess";
import { CameraBox, cameraSupported } from "./CameraBox";
import { toast } from "../ui/feedback";
import { Icon } from "../ui/Icon";
import { usePopupBack } from "../ui/usePopupBack";
import { useScrollLock } from "../useScrollLock";

// note giống bot để dữ liệu khớp Telegram
type Branch = { note: string; label: string; photo: boolean; done: boolean; hint?: string };

export function NopTienWizard({ threadId, onClose, onDone, adminQuick }: {
  threadId: string; onClose: () => void; onDone: () => void;
  /** admin: đánh dấu xong ngay bỏ qua ảnh — hiện nút phụ ở chân wizard */
  adminQuick?: () => void;
}) {
  usePopupBack(true, onClose);   // back → đóng wizard trước
  useScrollLock(true);           // khoá cuộn nền khi wizard mở
  const [step, setStep] = useState<"type" | "kytoa" | "photo">("type");
  const [branch, setBranch] = useState<Branch | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const marked = useRef(false);   // chống ghi task 2 lần (camera có thể chụp nhiều tấm)

  const markTask = async (note: string, done: boolean) => {
    await postJSON("/api/order/task", { thread_id: Number(threadId), type: "nop_tien", note, done }, { queueable: false });
    onDone();
    onClose();
  };

  // Camera đã upload 1 ảnh (vào /api/order/{id}/images → tự sang topic) → ghi task 1 lần.
  // note = '<code>;img:<id>' để dashboard biết ảnh nào là ảnh nộp tiền.
  const onPhotoUploaded = async (image?: any) => {
    if (marked.current || !branch) return;
    marked.current = true;
    const note = image?.id ? `${branch.note};img:${image.id}` : branch.note;
    try { await markTask(note, branch.done); toast(`✅ ${branch.label}`, "ok"); }
    catch (e: any) { marked.current = false; toast(e?.message || "Lỗi ghi nộp tiền", "err"); }
  };

  // Nhánh KHÔNG cần ảnh → ghi task luôn
  const pickNoPhoto = async (b: Branch) => {
    setBusy(true);
    try { await markTask(b.note, b.done); toast(`✅ ${b.label}`, "ok"); }
    catch (e: any) { toast(e?.message || "Lỗi ghi nộp tiền", "err"); setBusy(false); }
  };

  // Nhánh CẦN ảnh → mở bước chọn ảnh
  const pickPhoto = (b: Branch) => { setBranch(b); setStep("photo"); };

  const onFile = async (e: any) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f || !branch) return;
    setBusy(true);
    try {
      const p = await processImage(f);
      const fd = new FormData();
      fd.append("photo", p.full, `photo${p.ext}`);
      fd.append("thumb", p.thumb, `thumb${p.ext}`);
      fd.append("width", String(p.width));
      fd.append("height", String(p.height));
      const res = await postForm(`/api/order/${threadId}/images`, fd);   // → tự forward sang topic
      const note = res?.image?.id ? `${branch.note};img:${res.image.id}` : branch.note;
      await markTask(note, branch.done);
      toast(`✅ ${branch.label}`, "ok");
    } catch (ex: any) {
      toast(ex?.message || "Lỗi tải ảnh / ghi nộp tiền", "err");
      setBusy(false);
    }
  };

  return (
    <div class="modal-overlay" onClick={busy ? undefined : onClose}>
      <div class="modal-sheet nt-sheet" onClick={(e: any) => e.stopPropagation()}>
        <div class="modal-head"><Icon name="wallet" size={18} /> Nộp tiền {busy && "· ⏳"}</div>

        {step === "type" && (
          <>
            <button class="nt-opt" disabled={busy} onClick={() => pickPhoto({ note: "tra_tien_mat", label: "Báo khách trả đủ", photo: true, done: true })}>
              <Icon name="banknote" size={16} /> Báo khách <b>trả đủ</b>
              <span class="nt-sub">→ gửi ảnh tiền mặt + toa</span>
            </button>
            <button class="nt-opt" disabled={busy} onClick={() => setStep("kytoa")}>
              <Icon name="edit" size={16} /> Báo khách <b>nợ</b>
              <span class="nt-sub">→ chọn tình trạng ký toa</span>
            </button>
          </>
        )}

        {step === "kytoa" && (
          <>
            <button class="nt-opt" disabled={busy} onClick={() => pickPhoto({ note: "co_ky_toa", label: "Nợ · có ký toa", photo: true, done: true })}>
              <Icon name="edit" size={16} /> Có ký toa <span class="nt-sub">→ gửi ảnh toa có chữ ký</span>
            </button>
            <button class="nt-opt" disabled={busy} onClick={() => pickNoPhoto({ note: "khong_ky_toa", label: "Nợ · không ký toa", photo: false, done: true })}>
              <Icon name="ban" size={16} /> Không ký toa <span class="nt-sub">→ ghi nhận, không cần ảnh</span>
            </button>
            <button class="nt-opt" disabled={busy} onClick={() => pickNoPhoto({ note: "chieu_lay_tien", label: "Nợ · chiều lấy tiền", photo: false, done: false })}>
              <Icon name="clock" size={16} /> Chiều lấy tiền <span class="nt-sub">→ chưa xong, còn chờ thu</span>
            </button>
            <button class="btn small nt-back" disabled={busy} onClick={() => setStep("type")}>← Quay lại</button>
          </>
        )}

        {step === "photo" && branch && (
          <>
            <p class="nt-photo-hint">
              {branch.note === "tra_tien_mat" ? "Chụp ảnh tiền mặt + toa" : "Chụp ảnh toa có chữ ký"} <b>(bắt buộc)</b>
            </p>
            {cameraSupported() ? (
              // Cùng camera engine với khối Ảnh (in-page getUserMedia). Chụp 1 tấm → ghi task.
              <CameraBox base={`/api/order/${threadId}`} kind="nop_tien_task" onUploaded={onPhotoUploaded} onClose={onClose} />
            ) : (
              // Fallback không HTTPS: input capture của máy
              <>
                <input ref={fileInput} type="file" accept="image/*" capture="environment" hidden onChange={onFile} />
                <button class="btn primary block" disabled={busy} onClick={() => fileInput.current?.click()}>
                  {busy ? "⏳ Đang gửi…" : <><Icon name="camera" size={16} /> Chụp / Chọn ảnh</>}
                </button>
              </>
            )}
            {!busy && <button class="btn small nt-back" onClick={() => setStep(branch.note === "tra_tien_mat" ? "type" : "kytoa")}>← Quay lại</button>}
          </>
        )}

        {step === "type" && !busy && adminQuick && (
          <button class="btn small wz-admin" onClick={adminQuick} title="Admin: đánh dấu xong ngay, không cần ảnh">
            <Icon name="zap" size={14} /> Xong ngay — bỏ qua ảnh (admin)
          </button>
        )}
        {step !== "photo" && !busy && <button class="btn nt-cancel" onClick={onClose}>Huỷ</button>}
      </div>
    </div>
  );
}
