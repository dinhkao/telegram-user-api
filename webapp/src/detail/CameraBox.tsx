// Camera trực tiếp trong KHUNG (không fullscreen): mở luồng video 1 lần, chạm
// nút để chụp liên tiếp từng tấm — bắt frame <video> ra <canvas>, nén WebP
// (imageProcess.processSource) rồi upload /api/order/{id}/images. Nhanh vì camera
// chỉ khởi động MỘT lần (khác nút <input capture> mở lại OS camera mỗi tấm).
// CẦN secure context (HTTPS) — trên HTTP navigator.mediaDevices là undefined nên
// cameraSupported() = false, khung cha sẽ ẩn nút mở camera.
// Controlled: cha (Images) mount component này khi mở, gọi onClose để đóng.
// Data: POST /api/order/{thread_id}/images. onUploaded() để Images tải lại lưới.
import { useEffect, useRef, useState } from "preact/hooks";
import { createPortal } from "preact/compat";
import { postForm } from "../api";
import { processSource, processImage } from "./imageProcess";
import { Icon } from "../ui/Icon";
import { ErrorState } from "../ui/states";
import { useScrollLock } from "../useScrollLock";
import { usePopupBack } from "../ui/usePopupBack";

/** Trình duyệt/WebView có API camera trực tiếp không (cần HTTPS). */
export function cameraSupported(): boolean {
  return typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia;
}

/** Ảnh đã nén (full + thumb) chờ upload — dùng cho chế độ COLLECT (chụp trước, tạo
 *  entity sau rồi mới upload). */
export type Processed = { full: Blob; thumb: Blob; ext: string; width: number; height: number };

/** Upload 1 ảnh đã nén tới 1 entity base (`/api/media/…`). Tách ra để caller ở chế
 *  độ COLLECT tự upload sau khi entity được tạo. */
export function uploadProcessed(base: string, p: Processed, kind?: string) {
  const fd = new FormData();
  fd.append("photo", p.full, `photo${p.ext}`);
  fd.append("thumb", p.thumb, `thumb${p.ext}`);
  fd.append("width", String(p.width));
  fd.append("height", String(p.height));
  if (kind) fd.append("kind", kind);
  return postForm(`${base}/images`, fd);
}

function camError(ex: any): string {
  switch (ex?.name) {
    case "NotAllowedError":
      return "Bị chặn quyền camera. Cấp quyền camera cho app trong Cài đặt.";
    case "NotFoundError":
      return "Không tìm thấy camera trên máy.";
    case "NotReadableError":
      return "Camera đang bận (app khác đang dùng?).";
    default:
      return ex?.message || "Không mở được camera.";
  }
}

export function CameraBox({
  base,
  kind,
  extraBases,
  onClose,
  onUploaded,
  onCapture,
}: {
  base: string;
  kind?: string;                       // loại ảnh đơn (soạn hàng/nộp tiền…) — gắn cho mỗi tấm
  extraBases?: string[];               // mỗi tấm còn lưu THÊM vào các entity này (vd mọi thùng vừa tạo)
  onClose: () => void;
  onUploaded: (image?: any) => void;   // truyền ảnh vừa upload (id…) cho caller cần
  onCapture?: (p: Processed) => void;  // chế độ COLLECT: có prop này ⇒ KHÔNG upload,
                                       // chỉ trả ảnh đã nén cho caller giữ lại (tạo entity xong mới upload)
}) {
  const [busy, setBusy] = useState(false);
  const [shots, setShots] = useState(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const [flash, setFlash] = useState(false);
  const [err, setErr] = useState("");
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const stop = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
  };

  // Mở camera ngay khi mount; dọn khi unmount (đóng khung / rời trang)
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { ideal: "environment" }, // ưu tiên camera sau
            width: { ideal: 1920 },
            height: { ideal: 1080 },
          },
          audio: false,
        });
        if (!alive) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        const v = videoRef.current;
        if (v) {
          v.srcObject = stream;
          v.play().catch(() => {});
        }
      } catch (ex: any) {
        if (alive) setErr(camError(ex));
      }
    })();
    return () => {
      alive = false;
      stop();
    };
  }, []);

  // Upload 1 ảnh đã nén tới 1 base; withKind chỉ gắn kind cho base chính (ảnh đơn)
  const uploadTo = (b: string, p: Processed, withKind: boolean) =>
    uploadProcessed(b, p, withKind && kind ? kind : undefined);

  // Xử lý 1 ảnh đã nén: chế độ COLLECT → giao cho caller giữ; thường → upload ngay.
  const handleProcessed = async (p: Processed) => {
    if (onCapture) {
      onCapture(p);
      setShots((n) => n + 1);
      onUploaded();
      return;
    }
    const res = await uploadTo(base, p, true);
    await Promise.allSettled((extraBases || []).map((b) => uploadTo(b, p, false)));
    setShots((n) => n + 1);
    onUploaded(res?.image);
  };

  const shoot = async () => {
    const v = videoRef.current;
    if (!v || busy || !v.videoWidth) return;
    setBusy(true);
    setFlash(true);
    setTimeout(() => setFlash(false), 120);
    try {
      const canvas = document.createElement("canvas");
      canvas.width = v.videoWidth;
      canvas.height = v.videoHeight;
      canvas.getContext("2d")!.drawImage(v, 0, 0);
      const p = await processSource(canvas, canvas.width, canvas.height);
      await handleProcessed(p);
    } catch (ex: any) {
      setErr(ex?.message || "Chụp lỗi");
    } finally {
      setBusy(false);
    }
  };

  // CHỌN ẢNH TỪ MÁY ngay trong popup camera (thay chỗ chữ "Chạm để chụp"):
  // cùng pipeline nén/upload với ảnh chụp, chọn được nhiều tấm 1 lượt
  const pickFiles = async (files: FileList | null) => {
    if (!files || !files.length || busy) return;
    setBusy(true);
    try {
      for (const f of Array.from(files)) {
        if (!f.type.startsWith("image/")) continue;
        const p = await processImage(f);
        await handleProcessed(p);
      }
    } catch (ex: any) {
      setErr(ex?.message || "Tải ảnh lỗi");
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  useScrollLock(true);   // mount = camera đang mở → khoá cuộn nền
  usePopupBack(true, onClose);   // back → đóng camera trước

  // Popup toàn màn (portal ra body) — không nhúng trong khung/thẻ nữa.
  return createPortal(
    <div class="cam-overlay" onClick={(e: any) => { if (e.target === e.currentTarget) onClose(); }}>
      <div class="cambox">
        <div class="cam-view">
          <video ref={videoRef} autoPlay playsInline muted />
          {flash && <div class="cam-flash" />}
          {shots > 0 && <span class="cam-count">✓ {shots}</span>}
        </div>
        <div class="cam-bar">
          <button class="btn" onClick={onClose}>
            Xong{shots > 0 ? ` · ${shots} ảnh` : ""}
          </button>
          <button class="cam-shot" disabled={busy} onClick={shoot} aria-label="Chụp">
            {busy && <span class="img-spin" />}
          </button>
          <button class="btn cam-pick" disabled={busy} onClick={() => fileInput.current?.click()}>
            <Icon name="image" size={16} /> Chọn ảnh
          </button>
          <input ref={fileInput} type="file" accept="image/*" multiple hidden
            onChange={(e: any) => pickFiles(e.target.files)} />
        </div>
        {err && <ErrorState msg={err} />}
      </div>
    </div>,
    document.body,
  );
}
