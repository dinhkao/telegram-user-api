// Tải 1 file từ URL chạy được trên CẢ APK WebView lẫn trình duyệt. WebView không
// có DownloadListener nên window.open(url PDF) im lặng không tải gì (lỗi Duy gặp
// 2026-08-26) — dùng đúng pattern nút tải ảnh của PhotoViewer: fetch blob →
// Web Share (share sheet Android có "Lưu vào Tệp"/Zalo…) → fallback <a download>.
import { toast } from "./ui/feedback";

// Share sheet chỉ dành cho MÁY DI ĐỘNG (APK WebView không tải file được, iPhone
// lưu qua sheet "Lưu vào Tệp"). Desktop macOS cũng có navigator.share → không
// chặn thì bấm Tải lại ra popup share thay vì tải về máy.
export function preferShareSheet(): boolean {
  return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
}

export async function downloadFileFromUrl(url: string, name: string): Promise<void> {
  try {
    toast("Đang tải " + name + "…", "info");
    const res = await fetch(url);
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error(txt || `HTTP ${res.status}`);
    }
    const blob = await res.blob();
    const nav: any = navigator;
    const file = new File([blob], name, { type: blob.type || "application/octet-stream" });
    if (preferShareSheet() && nav.canShare && nav.canShare({ files: [file] })) {
      await nav.share({ files: [file], title: name });   // sheet tự báo, khỏi toast
      return;
    }
    const u = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = u;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(u), 1000);
    toast("Đã tải " + name, "ok");
  } catch (e: any) {
    if (e?.name === "AbortError") return;   // người dùng đóng share sheet
    toast(e?.message || "Tải không được", "err");
  }
}
