/** Đọc ẢNH đang có trong clipboard → File[] (nút "Dán" ở khối Ảnh).
 *  1) APK Android: WebView KHÔNG đọc được clipboard → cầu native
 *     `AndroidApp.clipboardImage()` trả data URL ("" = không có ảnh). APK cũ thiếu cầu → báo cập nhật.
 *  2) Trình duyệt (iPhone Safari/PWA, máy tính): navigator.clipboard.read() — phải gọi trong cú
 *     bấm; iPhone hiện nút "Dán" hệ thống để người dùng xác nhận.
 *  Lỗi ném Error với câu tiếng Việt dễ hiểu. */
function dataUrlToFile(dataUrl: string, i = 0): File {
  const [head, b64] = dataUrl.split(",", 2);
  const mime = /data:([^;]+)/.exec(head)?.[1] || "image/png";
  const bin = atob(b64 || "");
  const bytes = new Uint8Array(bin.length);
  for (let k = 0; k < bin.length; k++) bytes[k] = bin.charCodeAt(k);
  return new File([bytes], `clipboard-${Date.now()}-${i}.${mime.split("/")[1] || "png"}`, { type: mime });
}

export async function readClipboardImages(): Promise<File[]> {
  const app = (window as any).AndroidApp;
  if (app) {
    if (typeof app.clipboardImage !== "function") throw new Error("Cập nhật app (⚙️ Cài đặt) để dán được ảnh");
    const url = String(app.clipboardImage.call(app) || "");
    if (!url.startsWith("data:image/")) throw new Error("Clipboard không có ảnh — hãy sao chép (copy) 1 ảnh trước");
    return [dataUrlToFile(url)];
  }
  const cb: any = navigator.clipboard;
  if (!cb || typeof cb.read !== "function") throw new Error("Trình duyệt không cho dán ảnh bằng nút — dùng Ctrl+V");
  let items: any[];
  try {
    items = await cb.read();
  } catch (e: any) {
    if (e?.name === "NotAllowedError") throw new Error("Chưa cho phép đọc clipboard");
    throw new Error("Không đọc được clipboard");
  }
  const files: File[] = [];
  for (const it of items) {
    const t = (it.types as string[]).find((x) => x.startsWith("image/"));
    if (!t) continue;
    const blob: Blob = await it.getType(t);
    files.push(new File([blob], `clipboard-${Date.now()}-${files.length}.${t.split("/")[1] || "png"}`, { type: t }));
  }
  if (!files.length) throw new Error("Clipboard không có ảnh — hãy sao chép (copy) 1 ảnh trước");
  return files;
}

/** Ảnh trong sự kiện paste (Ctrl+V). Rỗng nếu không có ảnh. */
export function imagesFromPasteEvent(e: ClipboardEvent): File[] {
  return Array.from(e.clipboardData?.files || []).filter((f) => f.type.startsWith("image/"));
}
