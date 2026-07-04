// Camera trực tiếp trong KHUNG (không fullscreen): mở luồng video 1 lần, chạm
// nút để chụp liên tiếp từng tấm — bắt frame <video> ra <canvas>, nén WebP
// (imageProcess.processSource) rồi upload /api/order/{id}/images. Nhanh vì camera
// chỉ khởi động MỘT lần (khác nút 📸 <input capture> mở lại OS camera mỗi tấm).
// CẦN secure context (HTTPS) — trên HTTP LAN navigator.mediaDevices là undefined
// nên component tự ẩn, người dùng dùng nút 📸 Chụp cũ làm phương án dự phòng.
// Data: POST /api/order/{thread_id}/images. Gọi onUploaded() để Images tải lại lưới.
import { useEffect, useRef, useState } from "preact/hooks";
import { postForm } from "../api";
import { processSource } from "./imageProcess";

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

export function CameraBox({ threadId, onUploaded }: { threadId: string; onUploaded: () => void }) {
  const [on, setOn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [shots, setShots] = useState(0);
  const [flash, setFlash] = useState(false);
  const [err, setErr] = useState("");
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const supported =
    typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

  const stop = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
  };

  // Dọn camera khi rời trang / component unmount
  useEffect(() => () => stop(), []);

  const start = async () => {
    setErr("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: "environment" }, // ưu tiên camera sau
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
        audio: false,
      });
      streamRef.current = stream;
      setOn(true);
      setShots(0);
      // gán srcObject sau khi <video> đã render trong DOM
      requestAnimationFrame(() => {
        const v = videoRef.current;
        if (!v) return;
        v.srcObject = stream;
        v.play().catch(() => {});
      });
    } catch (ex: any) {
      setErr(camError(ex));
    }
  };

  const close = () => {
    stop();
    setOn(false);
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
      const fd = new FormData();
      fd.append("photo", p.full, `photo${p.ext}`);
      fd.append("thumb", p.thumb, `thumb${p.ext}`);
      fd.append("width", String(p.width));
      fd.append("height", String(p.height));
      await postForm(`/api/order/${threadId}/images`, fd);
      setShots((n) => n + 1);
      onUploaded();
    } catch (ex: any) {
      setErr(ex?.message || "Chụp lỗi");
    } finally {
      setBusy(false);
    }
  };

  if (!supported) return null; // thiếu HTTPS/camera API → ẩn, dùng nút 📸 Chụp

  if (!on)
    return (
      <div class="cam-open">
        <button class="btn" onClick={start}>🎥 Mở camera</button>
        {err && <p class="error small">{err}</p>}
      </div>
    );

  return (
    <div class="cambox">
      <div class="cam-view">
        <video ref={videoRef} autoPlay playsInline muted />
        {flash && <div class="cam-flash" />}
        {shots > 0 && <span class="cam-count">✓ {shots}</span>}
      </div>
      <div class="cam-bar">
        <button class="btn" onClick={close}>Xong{shots > 0 ? ` (${shots})` : ""}</button>
        <button class="cam-shot" disabled={busy} onClick={shoot} aria-label="Chụp">
          {busy && <span class="img-spin" />}
        </button>
        <span class="muted small">Chạm để chụp</span>
      </div>
      {err && <p class="error small">{err}</p>}
    </div>
  );
}
