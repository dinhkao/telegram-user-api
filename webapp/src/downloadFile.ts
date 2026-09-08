// Tải 1 file từ URL chạy được trên CẢ APK WebView lẫn trình duyệt. WebView không
// có DownloadListener nên window.open(url PDF) im lặng không tải gì (lỗi Duy gặp
// 2026-08-26) — dùng đúng pattern nút tải ảnh của PhotoViewer: fetch blob →
// APK: cầu native AndroidApp.saveFile (Download/LeTrangPhat) → iPhone/trình duyệt
// di động: Web Share (sheet có "Lưu vào Tệp"/Zalo…) → desktop: <a download>.
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
    // APK WebView: KHÔNG có Web Share, KHÔNG có DownloadListener → <a download> im
    // lặng (Duy gặp 2026-09-08: "bấm tải PDF, trong máy không thấy file" mà app
    // vẫn báo Đã tải). Đi qua cầu native AndroidApp.saveFile → Download/LeTrangPhat
    // + thông báo hệ thống bấm mở. APK cũ chưa có cầu này thì báo thẳng, không giả
    // vờ thành công.
    const bridge: any = (window as any).AndroidApp;
    if (bridge) {
      if (typeof bridge.saveFile !== "function") {
        throw new Error("App chưa hỗ trợ tải file — cập nhật app (⚙ → Cập nhật) rồi tải lại");
      }
      const dataUrl: string = await new Promise((res2, rej) => {
        const fr = new FileReader();
        fr.onload = () => res2(String(fr.result));
        fr.onerror = () => rej(new Error("Đọc file lỗi"));
        fr.readAsDataURL(blob);
      });
      const ok = bridge.saveFile(dataUrl, name);
      if (ok === false) throw new Error("Lưu file lỗi — máy chặn ghi vào Download?");
      toast("Đã lưu " + name + " vào Download/LeTrangPhat", "ok");
      return;
    }
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
